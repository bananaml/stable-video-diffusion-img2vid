from potassium import Potassium, Request, Response
import torch

import math
import os
from glob import glob
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
import torch
from einops import rearrange, repeat
from fire import Fire
from PIL import Image
from torchvision.transforms import ToTensor
from sgm.inference.helpers import embed_watermark
from sgm.util import default, instantiate_from_config
from omegaconf import OmegaConf
import base64
import io
import requests

app = Potassium("stable-video-diffusion")

# @app.init runs at startup, and loads models into the app's context
@app.init
def init():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    config = "generative-models/scripts/sampling/configs/svd.yaml"
    num_frames = 14
    num_steps = 25
    config = OmegaConf.load(config)
    if device == "cuda":
        config.model.params.conditioner_config.params.emb_models[
            0
        ].params.open_clip_embedding_config.params.init_device = device

    config.model.params.sampler_config.params.num_steps = num_steps
    config.model.params.sampler_config.params.guider_config.params.num_frames = (
        num_frames
    )
    
    torch.manual_seed(23)

    if device == "cuda":
        with torch.device(device):
            model = instantiate_from_config(config.model).to(device).eval()
    else:
        model = instantiate_from_config(config.model).to(device).eval()

    context = {
        "model": model,
        "device": device,
        "num_frames": num_frames,
        "num_steps": num_steps,
        "config": config,
    }

    return context

def get_unique_embedder_keys_from_conditioner(conditioner):
    return list(set([x.input_key for x in conditioner.embedders]))


def get_batch(keys, value_dict, N, T, device):
    batch = {}
    batch_uc = {}

    for key in keys:
        if key == "fps_id":
            batch[key] = (
                torch.tensor([value_dict["fps_id"]])
                .to(device)
                .repeat(int(math.prod(N)))
            )
        elif key == "motion_bucket_id":
            batch[key] = (
                torch.tensor([value_dict["motion_bucket_id"]])
                .to(device)
                .repeat(int(math.prod(N)))
            )
        elif key == "cond_aug":
            batch[key] = repeat(
                torch.tensor([value_dict["cond_aug"]]).to(device),
                "1 -> b",
                b=math.prod(N),
            )
        elif key == "cond_frames":
            batch[key] = repeat(value_dict["cond_frames"], "1 ... -> b ...", b=N[0])
        elif key == "cond_frames_without_noise":
            batch[key] = repeat(
                value_dict["cond_frames_without_noise"], "1 ... -> b ...", b=N[0]
            )
        else:
            batch[key] = value_dict[key]

    if T is not None:
        batch["num_video_frames"] = T

    for key in batch.keys():
        if key not in batch_uc and isinstance(batch[key], torch.Tensor):
            batch_uc[key] = torch.clone(batch[key])
    return batch, batch_uc


# @app.handler runs for every call
@app.handler("/")
def handler(context: dict, request: Request) -> Response:
    # -------------------------
    # Constants and Context

    fps_id: int = 6
    motion_bucket_id: int = 127
    cond_aug: float = 0.02
    default_input = "generative-models/assets/test_image.png"
    output_folder = "outputs"
    video_path = os.path.join(output_folder, "out.mp4")


    device = context.get("device")
    model = context.get("model")
    num_frames = context.get("num_frames")

    # -------------------------
    # User Params

    # Tweak to prevent OOM
    decoding_t = request.json.get("decoding_t", 1)
    max_dimension = request.json.get("max_dimension", 1024)

    # For random seeding
    seed = request.json.get("seed")
    if seed != None:
        torch.manual_seed(seed)

    # Image passed in via json
    if request.json.get("image_bytes") != None:
        image_bytes = base64.b64decode(request.json.get("image_bytes"))
        image = Image.open(io.BytesIO(image_bytes))
    
    # Image passed in via url
    elif request.json.get("image_url") != None:
        response = requests.get(request.json.get("image_url"))
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
    
    # Default rocket img
    else:
        print("Using default image 🚀")
        input_img_path = Path(default_input)
        image = Image.open(input_img_path)

    # -------------------------
    # Generate!

    if image.mode == "RGBA":
        image = image.convert("RGB")
    w, h = image.size

    # Shrink to max dimension to prevent OOM
    scale = min(max_dimension / w, max_dimension / h)
    w, h = int(w * scale), int(h * scale)
    image = image.resize((w, h))
    print(f"Resized image to {h}x{w}")

    if h % 64 != 0 or w % 64 != 0:
        width, height = map(lambda x: x - x % 64, (w, h))
        image = image.resize((width, height))
        print(
            f"WARNING: Your image is of size {h}x{w} which is not divisible by 64. We are resizing to {height}x{width}!"
        )

    image = ToTensor()(image)
    image = image * 2.0 - 1.0

    image = image.unsqueeze(0).to(device)
    H, W = image.shape[2:]
    assert image.shape[1] == 3
    F = 8
    C = 4
    shape = (num_frames, C, H // F, W // F)
    if (H, W) != (576, 1024):
        print(
            "WARNING: The conditioning frame you provided is not 576x1024. This leads to suboptimal performance as model was only trained on 576x1024. Consider increasing `cond_aug`."
        )
    if motion_bucket_id > 255:
        print(
            "WARNING: High motion bucket! This may lead to suboptimal performance."
        )

    if fps_id < 5:
        print("WARNING: Small fps value! This may lead to suboptimal performance.")

    if fps_id > 30:
        print("WARNING: Large fps value! This may lead to suboptimal performance.")

    value_dict = {}
    value_dict["motion_bucket_id"] = motion_bucket_id
    value_dict["fps_id"] = fps_id
    value_dict["cond_aug"] = cond_aug
    value_dict["cond_frames_without_noise"] = image
    value_dict["cond_frames"] = image + cond_aug * torch.randn_like(image)
    value_dict["cond_aug"] = cond_aug

    with torch.no_grad():
        with torch.autocast(device):
            batch, batch_uc = get_batch(
                get_unique_embedder_keys_from_conditioner(model.conditioner),
                value_dict,
                [1, num_frames],
                T=num_frames,
                device=device,
            )
            c, uc = model.conditioner.get_unconditional_conditioning(
                batch,
                batch_uc=batch_uc,
                force_uc_zero_embeddings=[
                    "cond_frames",
                    "cond_frames_without_noise",
                ],
            )

            for k in ["crossattn", "concat"]:
                uc[k] = repeat(uc[k], "b ... -> b t ...", t=num_frames)
                uc[k] = rearrange(uc[k], "b t ... -> (b t) ...", t=num_frames)
                c[k] = repeat(c[k], "b ... -> b t ...", t=num_frames)
                c[k] = rearrange(c[k], "b t ... -> (b t) ...", t=num_frames)

            randn = torch.randn(shape, device=device)

            additional_model_inputs = {}
            additional_model_inputs["image_only_indicator"] = torch.zeros(
                2, num_frames
            ).to(device)
            additional_model_inputs["num_video_frames"] = batch["num_video_frames"]

            def denoiser(input, sigma, c):
                return model.denoiser(
                    model.model, input, sigma, c, **additional_model_inputs
                )

            samples_z = model.sampler(denoiser, randn, cond=c, uc=uc)
            model.en_and_decode_n_samples_a_time = decoding_t
            samples_x = model.decode_first_stage(samples_z)
            samples = torch.clamp((samples_x + 1.0) / 2.0, min=0.0, max=1.0)

            os.makedirs(output_folder, exist_ok=True)

            writer = cv2.VideoWriter(
                video_path,
                cv2.VideoWriter_fourcc(*"MP4V"),
                fps_id + 1,
                (samples.shape[-1], samples.shape[-2]),
            )

            samples = embed_watermark(samples)
            # samples = filter(samples)
            vid = (
                (rearrange(samples, "t c h w -> t h w c") * 255)
                .cpu()
                .numpy()
                .astype(np.uint8)
            )
            for frame in vid:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                writer.write(frame)
            writer.release()

    # Read output file into bytes
    with open(video_path, "rb") as video_file:
        encoded_string = base64.b64encode(video_file.read())
    mp4_bytes = encoded_string.decode('utf-8')

    return Response(
        json = {"mp4_bytes": mp4_bytes}, 
        status=200
    )

if __name__ == "__main__":
    app.serve()