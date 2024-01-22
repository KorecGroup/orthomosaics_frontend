from json import dumps, load, loads
from pathlib import Path

from pandas import DataFrame
from requests import get, post
from streamlit import (
    button,
    data_editor,
    error,
    file_uploader,
    form,
    form_submit_button,
    image,
    info,
    set_page_config,
    status,
    success,
    warning,
)

from utils import decode_image, encode_image

set_page_config(page_title="Orthomosaics", page_icon="📍")
endpoint = "https://ortho-mosaic.azurewebsites.net/orthomosaic/"

metadata = None
metadata_path = Path(f"origin.json")
if metadata_path.is_file():
    with metadata_path.open() as file:
        metadata = load(file)

orthomosaic_id = metadata["id"] if metadata else None
success(f"Orthomosaic ID = {orthomosaic_id}")
if orthomosaic_id:
    image_path = Path(f"orthomosaic.png")
    refresh_button = button(label="Refresh Orthomosaic")

    if not image_path.is_file() or refresh_button:
        with status("Downloading tiles..."), get(
            endpoint + f"?orthomosaic_id={orthomosaic_id}", stream=True
        ) as response_stream:
            if response_stream.ok:
                try:
                    for response in response_stream.iter_lines():
                        result = loads(response)
                        image_bytes = result["image"]
                        info(result["status_message"])
                        if image_bytes:
                            with open("orthmosaic.png", "wb") as file:
                                file.write(decode_image(image_b64=image_bytes))
                except Exception as e:
                    error(e)
            else:
                error(response_stream.reason)
                error(loads(response_stream.json(), indent=2))

    if image_path.is_file():
        image(str(image_path), caption=orthomosaic_id)


uploaded_backdown_image = file_uploader("Add another backdown image to the Orthomosaic")
if uploaded_backdown_image:
    with form("Upload Backdown Image"):
        default_settings = DataFrame(
            [
                {"feature": "camera", "key": "roll", "value": -0.7785},
                {"feature": "camera", "key": "pitch", "value": -47.34954},
                {"feature": "GPS", "key": "heading", "value": 27.09975},
                {"feature": "GPS", "key": "x", "value": 572731.967},
                {"feature": "GPS", "key": "y", "value": 273978.545},
            ]
        )
        settings = data_editor(
            default_settings,
            disabled=["feature", "key"],
            hide_index=True,
        )

        metadata = None
        if orthomosaic_id:
            warning(f"Backdown image will be added to: {orthomosaic_id}")
            metadata_path = Path(f"origin.json")
            if metadata_path.is_file():
                with metadata_path.open() as file:
                    metadata = load(file)
        else:
            warning("No orthomosaic id provided. Image will create a new orthomosaic")

        submit_button = form_submit_button("Add Backdown Image to Orthomosaic")
        if submit_button:
            with status("Uploading Backdown Image..."), post(
                url=endpoint,
                json=dict(
                    backdown_image_b64=encode_image(
                        image_bytes=uploaded_backdown_image.getvalue()
                    ),
                    gps=dict(
                        x=settings[settings["key"] == "x"].values[0][-1],
                        y=settings[settings["key"] == "y"].values[0][-1],
                        heading=settings[settings["key"] == "heading"].values[0][-1],
                    ),
                    backdown_image_metadata=dict(
                        roll_deg=settings[settings["key"] == "roll"].values[0][-1],
                        pitch_deg=settings[settings["key"] == "pitch"].values[0][-1],
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
                                success(metadata)
                                with open("origin.json", "w") as file:
                                    file.write(dumps(metadata, indent=2))
                    except Exception as e:
                        error(e)
                else:
                    error(response_stream.reason)
                    error(response_stream.json())
