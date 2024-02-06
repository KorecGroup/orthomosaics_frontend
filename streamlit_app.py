from base64 import b64decode, b64encode
from copy import deepcopy
from csv import Sniffer
from io import BytesIO, StringIO
from json import loads

from pandas import DataFrame, read_csv
from requests import get, post
from streamlit import (
    checkbox,
    error,
    file_uploader,
    form,
    form_submit_button,
    image,
    info,
    number_input,
    progress,
    session_state,
    set_page_config,
    status,
    success,
    table,
    tabs,
    text_input,
    toggle,
    warning,
)


def encode_image(image_bytes: str) -> str:
    return b64encode(image_bytes).decode()


def decode_image(image_b64: str) -> BytesIO:
    return BytesIO(b64decode(image_b64))


def detect_delimiter(file: StringIO) -> str:
    return Sniffer().sniff(deepcopy(file).read()).delimiter


set_page_config(page_title="Orthomosaics", page_icon="📍")
endpoint = "https://ortho-mosaic.azurewebsites.net/orthomosaic/"


upload_azure_tab, upload_local_tab, download_tab, orthorectify_tab = tabs(
    [
        "Create Orthomosaic (via Azure Storage)",
        "Update Orthomosaic",
        "Download Orthomosaic",
        "Orthorectify",
    ]
)


with download_tab:
    with form("Download Orthomosaic"):
        orthomosaic_id = session_state.get("orthomosaic_id")
        orthomosaic_id = text_input(
            label="Orthomosaic id", value=orthomosaic_id if orthomosaic_id else ""
        )
        resolution = 0.1
        originX = 0
        originY = 0
        submit_button = form_submit_button("Reload")
        if submit_button and orthomosaic_id:
            with status(f"Downloading tiles for orthomosaic {orthomosaic_id}..."), get(
                endpoint
                + f"?orthomosaic_id={orthomosaic_id}&resolution={resolution}&origin_x={originX}&origin_y={originY}",
                stream=True,
            ) as response_stream:
                if response_stream.ok:
                    try:
                        session_state["orthomosaic"] = ""
                        for response in response_stream.iter_lines():
                            result = loads(response)
                            image_bytes_chunk = result["image"]
                            info(result["status_message"])
                            if image_bytes_chunk:
                                session_state["orthomosaic"] += image_bytes_chunk
                    except Exception as e:
                        error(e)
                else:
                    error(response_stream.reason)

        image_bytes = session_state.get("orthomosaic")
        if image_bytes:
            image(decode_image(image_b64=image_bytes))

with upload_azure_tab:
    with form("Upload Via Azure Storage"):
        location = text_input("Location (name of folder in azure storage)")
        side_crop_pixels = number_input(
            label="Side Crop (pixels)", value=0, min_value=0, max_value=1000
        )
        submit_button = form_submit_button("Process")
        if submit_button and location:
            with status(f"Downloading images from Azure Storage: {location}..."), post(
                url=f"{endpoint}/update/folder/",
                json=dict(location=location, side_crop_pixels=side_crop_pixels),
                stream=True,
            ) as response_stream:
                if response_stream.ok:
                    try:
                        for response in response_stream.iter_lines():
                            result = loads(response)
                            session_state["orthomosaic_id"] = result["orthomosaic_id"]
                            message = result["status_message"]
                            if message.startswith("Progress"):
                                success(message)
                                success(
                                    f"Orthomosaics: {session_state['orthomosaic_id']}"
                                )
                            else:
                                info(message)
                    except Exception as e:
                        error(e)
                else:
                    error(response_stream.reason)
            success(f"Orthomosaic complete ({session_state['orthomosaic_id']})")

with orthorectify_tab:
    uploaded_backdown_image = file_uploader(
        label="Backdown image",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=False,
    )
    if uploaded_backdown_image:
        image(uploaded_backdown_image)
        with form("Orthorectify Backdown Image"):
            roll = number_input(label="Camera Roll", value=0.0)
            pitch = number_input(label="Camera Pitch", value=-48.0)
            submit_button = form_submit_button("Orthorectify")
            if submit_button and (pitch or roll):
                with post(
                    url="https://ortho-mosaic.azurewebsites.net/orthorectify/image/",
                    json=dict(
                        backdown_image_b64=encode_image(
                            image_bytes=uploaded_backdown_image.read()
                        ),
                        gps=dict(
                            x=0.0,
                            y=0.0,
                            heading=0.0,
                        ),
                        backdown_image_metadata=dict(
                            roll_deg=roll,
                            pitch_deg=pitch,
                        ),
                        orthomosaic_id=orthomosaic_id,
                    ),
                    stream=True,
                ) as response:
                    if response.ok:
                        session_state["orthorectified"] = BytesIO(response.content)
                    else:
                        error(response_stream.reason)
            image_bytes = session_state.get("orthorectified")
            if image_bytes:
                image(image_bytes)


with upload_local_tab:
    with form("Upload Backdown Image"):
        uploaded_backdown_images = file_uploader(
            label="Backdown images to generate Orthomosaic and a single (csv) file to specify GPS and Camera settings",
            type=["png", "jpg", "jpeg", "csv"],
            accept_multiple_files=True,
        )

        settings_file = None
        settings_files = list(
            filter(lambda file: file.name.endswith("csv"), uploaded_backdown_images)
        )
        if any(settings_files):
            if len(settings_files) > 1:
                warning(
                    "Multiple settings files detected. Only the first will be considered"
                )
            settings_file = settings_files[0]

        image_files = []
        for uploaded_file in uploaded_backdown_images:
            if uploaded_file not in settings_files:
                image_files.append(uploaded_file)

        image_names = list(
            map(
                lambda file: file.name.strip(".jpg").strip(".jpeg").strip(".png"),
                image_files,
            )
        )
        settings_relevant = []
        settings_errors = 0
        default_pitch = -48.0
        settings_key_pitch = "pitch[deg]"
        setting_keys = (
            "roll[deg]",
            settings_key_pitch,
            "heading[deg]",
            "projectedX[m]",
            "projectedY[m]",
        )
        if settings_file:
            delimiter = detect_delimiter(
                file=StringIO(settings_file.getvalue().decode("utf-8"))
            )
            warning(f"{delimiter} delimiter detected for settings file")
            settings = read_csv(settings_file, delimiter=delimiter)
            for key in setting_keys:
                if key not in settings:
                    error(
                        f"Could not find column '{key}' in settings file {settings_file.name}"
                    )
                    settings_errors += 1
            if "file_name" not in settings:
                error(
                    f"Could not find column 'file_name' in settings file {settings_file.name}"
                )
                settings_errors += 1
            else:
                for image_name in image_names:
                    if image_name not in settings["file_name"].values:
                        error(f"No settings were provided for image: {image_name}")
                        settings_errors += 1
                        settings_relevant.append({key: None for key in setting_keys})
                    else:
                        data = settings[settings["file_name"] == image_name]
                        pitch = data[settings_key_pitch].values[0]
                        pitch_is_valid = 0 > pitch > -90
                        if not pitch_is_valid:
                            warning(
                                f"Invalid pitch {pitch}. Using default value {default_pitch}"
                            )
                            data[settings_key_pitch] = default_pitch
                        settings_relevant.append(
                            {key: data[key].values[0] for key in setting_keys}
                        )

            if any(settings_relevant):
                settings = DataFrame(settings_relevant, index=image_names)

            table(settings.head())

        submit_button = form_submit_button("Submit Backdown Images")
        side_crop_pixels = number_input(
            label="Side Crop (pixels)", value=0, min_value=0, max_value=1000
        )
        custom_metadata_button = toggle("Add to existing Orthomosaic")

        if custom_metadata_button:
            orthomosaic_id = session_state.get("orthomosaic_id")
            try:
                orthomosaic_id = text_input(
                    "Orthomosaic ID:", value=orthomosaic_id if orthomosaic_id else ""
                )
                if not orthomosaic_id.startswith("orthomosaic_"):
                    raise ValueError(f"{orthomosaic_id} is an invalid id")
            except ValueError as e:
                error(e)
            session_state["metadata_confirmed"] = checkbox("Confirm")
        else:
            orthomosaic_id = None

        if submit_button:
            if not any(image_files):
                error("Please add at least one backdown image")
            elif not settings_file:
                error(
                    "Please also include a (csv) file to specify the gps and camera settings for the images provided"
                )
            elif settings_errors:
                error(f"Please fix errors related to the settings (csv file)")
            elif custom_metadata_button and not session_state.get("metadata_confirmed"):
                error(
                    "Please confirm the orthomosaic reference point you wish to add to"
                )
            else:
                n = len(image_files)
                for i, image in enumerate(image_files):
                    progress((i + 1) / n)
                    session_state["orthomosaic_id"] = orthomosaic_id
                    with status(
                        f"Adding Backdown Image {image.name} to Orthomosaic {orthomosaic_id}"
                    ), post(
                        url=f"{endpoint}update/image/",
                        json=dict(
                            backdown_image_b64=encode_image(image_bytes=image.read()),
                            gps=dict(
                                x=settings.iloc[i]["projectedX[m]"],
                                y=settings.iloc[i]["projectedY[m]"],
                                heading=settings.iloc[i]["heading[deg]"],
                            ),
                            backdown_image_metadata=dict(
                                roll_deg=settings.iloc[i]["roll[deg]"],
                                pitch_deg=settings.iloc[i]["pitch[deg]"],
                            ),
                            orthomosaic_id=orthomosaic_id,
                            side_crop_pixels=side_crop_pixels,
                        ),
                        stream=True,
                    ) as response_stream:
                        if response_stream.ok:
                            try:
                                for response in response_stream.iter_lines():
                                    result = loads(response)
                                    info(result["status_message"])
                                    session_state["orthomosaic_id"] = result[
                                        "orthomosaic_id"
                                    ]
                            except Exception as e:
                                error(e)
                        else:
                            error(response_stream.reason)
                success(f"Orthomosaic complete ({session_state['orthomosaic_id']})")
