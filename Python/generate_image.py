"""
generate_image.py — lightweight reference image generator for the HY3D pipeline.

Runs as a short-lived subprocess: loads model, generates one PNG, exits.
All VRAM is released on exit before HY3D spawns.

Usage:
    python generate_image.py <prompt> <output_png> <seed> [model_safetensors_path]

Exit codes: 0 = success, 1 = failure (error printed to stderr).
"""
import sys
import torch
from pathlib import Path

def main():
    if len(sys.argv) < 3:
        print("Usage: generate_image.py <prompt> <output_png> [seed] [model_path]",
              file=sys.stderr)
        sys.exit(1)

    prompt     = sys.argv[1]
    output     = Path(sys.argv[2])
    seed       = int(sys.argv[3]) if len(sys.argv) > 3 else 1234
    model_path = sys.argv[4] if len(sys.argv) > 4 else None

    neg_prompt = (
        "blurry, low quality, flat shading, 2d, anime, cartoon, deformed, "
        "extra limbs, bad anatomy, ugly, watermark, text"
    )

    print(f"Loading model...", flush=True)

    from diffusers import StableDiffusionXLPipeline
    import torch

    if model_path and Path(model_path).exists():
        pipe = StableDiffusionXLPipeline.from_single_file(
            model_path,
            torch_dtype=torch.float16,
            use_safetensors=True,
        )
        print(f"Loaded local model: {Path(model_path).name}", flush=True)
    else:
        # Fallback: download SD 1.5 (small, ~2 GB)
        from diffusers import StableDiffusionPipeline
        pipe = StableDiffusionPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            torch_dtype=torch.float16,
            safety_checker=None,
        )
        print("Loaded runwayml/stable-diffusion-v1-5 (HuggingFace)", flush=True)

    pipe = pipe.to("cuda")
    pipe.enable_attention_slicing()

    print(f"Generating image (seed={seed})...", flush=True)
    generator = torch.Generator(device="cuda").manual_seed(seed)

    result = pipe(
        prompt=prompt,
        negative_prompt=neg_prompt,
        num_inference_steps=25,
        guidance_scale=7.0,
        width=768,
        height=768,
        generator=generator,
    )
    image = result.images[0]

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output))
    print(f"Saved: {output}", flush=True)


if __name__ == "__main__":
    main()
