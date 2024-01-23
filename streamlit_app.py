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

from utils import decode_image, encode_image

set_page_config(page_title="Orthomosaics", page_icon="📍")
endpoint = "https://ortho-mosaic.azurewebsites.net/orthomosaic/"


upload_tab, download_tab = tabs(["Upload", "Download"])

with download_tab:
    with form("Download Orthomosaic"):
        metadata = session_state.get("orthomosaic_metadata")
        orthomosaic_id = text_input(
            label="Orthomosaic id", value=metadata["id"] if metadata else ""
        )

        submit_button = form_submit_button("Reload")
        if submit_button:
            with status(f"Downloading tiles for orthomosaic {orthomosaic_id}..."), get(
                endpoint + f"?orthomosaic_id={orthomosaic_id}", stream=True
            ) as response_stream:
                if response_stream.ok:
                    try:
                        for response in response_stream.iter_lines():
                            result = loads(response)
                            image_bytes = result["image"]
                            info(result["status_message"])
                            if image_bytes:
                                session_state["orthomosaic"] = decode_image(
                                    image_b64=image_bytes
                                )
                    except Exception as e:
                        error(e)
                else:
                    error(response_stream.reason)
                    error(loads(response_stream.json(), indent=2))

        image_bytes = session_state.get("orthomosaic")
        if image_bytes:
            image(image_bytes)


with upload_tab:
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
        setting_keys = (
            "roll[deg]",
            "pitch[deg]",
            "heading[deg]",
            "projectedX[m]",
            "projectedY[m]",
        )
        if settings_file:
            settings = read_csv(settings_file)
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
                        settings_relevant.append(
                            {key: data[key].values[0] for key in setting_keys}
                        )

            if any(settings_relevant):
                settings = DataFrame(settings_relevant, index=image_names)

            table(settings.head())

        submit_button = form_submit_button("Submit Backdown Images")
        custom_metadata_button = toggle("Add to existing Orthomosaic")

        if custom_metadata_button:
            metadata = session_state.get("orthomosaic_metadata")
            try:
                metadata = {
                    "id": text_input(
                        "Orthomosaic ID:", value=metadata["id"] if metadata else ""
                    ),
                    "x_m": float(
                        text_input(
                            "GPS X:", value=metadata["x_m"] if metadata else "0.0"
                        )
                    ),
                    "y_m": float(
                        text_input(
                            "GPS Y:", value=metadata["y_m"] if metadata else "0.0"
                        )
                    ),
                    "x_m_per_pixel": float(
                        text_input(
                            "X metres per pixel:",
                            value=metadata["x_m_per_pixel"] if metadata else "0.0",
                        )
                    ),
                    "y_m_per_pixel": float(
                        text_input(
                            "Y metres per pixel:",
                            value=metadata["y_m_per_pixel"] if metadata else "0.0",
                        )
                    ),
                }
                if not metadata["id"].startswith("orthomosaic_"):
                    raise ValueError(f"{metadata['id']} is an invalid id")
            except ValueError as e:
                error(e)
            session_state["metadata_confirmed"] = checkbox("Confirm")
        else:
            metadata = None

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

                    with status(
                        f"Adding Backdown Image {image.name} to Orthomosaic {metadata}"
                    ), post(
                        url=endpoint,
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
                            orthomosaic_metadata=metadata,
                        ),
                        stream=True,
                    ) as response_stream:
                        if response_stream.ok:
                            try:
                                for response in response_stream.iter_lines():
                                    result = loads(response)
                                    info(result["status_message"])
                                    metadata = result["orthomosaic_metadata"]
                                    if metadata:
                                        session_state["orthomosaic_metadata"] = metadata
                                        success(metadata)
                            except Exception as e:
                                error(e)
                        else:
                            error(response_stream.reason)
                            error(response_stream.json())
                success(
                    f"Orthomosaic complete ({session_state['orthomosaic_metadata']})"
                )
