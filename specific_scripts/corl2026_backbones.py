"""Find the backbone models each CoRL 2026 paper uses, by matching known model names in the PDF text before References.

Writes website/corl2026/backbones.json: {paper_id: [model names]}; website/corl2026/build.py turns the top 50 into a filter.

    uv run python specific_scripts/corl2026_backbones.py
"""

import collections
import glob
import json
import os
import re

import pymupdf

from corl2026_robots import MIN_MENTIONS, REFS_RE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "website", "corl2026")
OUT = os.path.join(HERE, "backbones.json")

# canonical name -> regex; vision encoders, LLMs / VLMs, robot foundation models (VLAs), policy and world-model families
BACKBONES = {
    # vision encoders
    "ResNet": r"\bResNet-?\d*\b",
    "ViT": r"\bViT\b|Vision Transformer",
    "DINO / DINOv2 / DINOv3": r"(?<!Grounding )(?<!Grounding-)\bDINO(?:-?v[23])?\b",
    "Grounding DINO": r"Grounding[- ]?DINO",
    "CLIP": r"\bCLIP\b",
    "SigLIP": r"\bSigLIP",
    "SAM / SAM 2": r"\bSAM ?2?\b|Segment Anything",
    "Depth Anything": r"Depth[- ]Anything",
    "EfficientNet": r"\bEfficientNet",
    "R3M": r"\bR3M\b",
    "VC-1": r"\bVC-1\b",
    "PointNet / PointNet++": r"\bPointNet",
    "U-Net": r"\bU-?Net\b",
    "V-JEPA": r"\bV-JEPA",
    # language and vision-language models
    "PaliGemma": r"\bPaliGemma",
    "Gemma": r"\bGemma\b",
    "Llama": r"\bL(?:lama|LaMA|LAMA)",
    "LLaVA": r"\bLLaVA",
    "Qwen (Qwen-VL / Qwen2.5-VL)": r"\bQwen",
    "GPT-4 / GPT-4o / GPT-5": r"\bGPT-?[45]",
    "Gemini": r"\bGemini\b",
    "Claude": r"\bClaude\b",
    "Florence-2": r"\bFlorence-?2\b",
    "Prismatic": r"\bPrismatic\b",
    # robot foundation models (VLAs)
    "π0 / π0.5": r"π\s*0|\bpi[_ -]?0(?:\.5)?\b|\bPi0",
    "OpenVLA / OpenVLA-OFT": r"\bOpenVLA",
    "Octo": r"\bOcto\b",
    "RT-1 / RT-2 / RT-X": r"\bRT-[12X]\b",
    "GR00T": r"\bGR00T\b|\bGROOT\b",
    "RDT": r"\bRDT(?:-1B)?\b",
    "SmolVLA": r"\bSmolVLA",
    "CogACT": r"\bCogACT",
    "UniVLA": r"\bUniVLA",
    # policy, generative and world-model families
    "Diffusion Policy": r"\bDiffusion Polic(?:y|ies)\b",
    "DP3 (3D Diffusion Policy)": r"\bDP3\b|3D Diffusion Policy",
    "ACT (Action Chunking Transformer)": r"\bACT\b|Action Chunking (?:with )?Transformers?",
    "Stable Diffusion": r"\bStable Diffusion",
    "Wan (video model)": r"\bWan ?2\.[12]\b",
    "Cosmos": r"\bCosmos\b",
    "DreamerV3": r"\bDreamer(?:V[23])?\b",
    "Mamba": r"\bMamba\b",
}
BACKBONE_RES = {k: re.compile(v) for k, v in BACKBONES.items()}


def backbones(text):
    text = REFS_RE.split(text)[0].replace("\n", " ")
    return [k for k, rx in BACKBONE_RES.items() if len(rx.findall(text)) >= MIN_MENTIONS]


def main():
    out = {}
    for p in sorted(glob.glob(os.path.join(HERE, "pdfs", "*.pdf"))):
        with pymupdf.open(p) as doc:
            found = backbones("\n".join(page.get_text() for page in doc))
        if found:
            out[os.path.basename(p).split("_", 1)[0]] = found
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    counts = collections.Counter(b for v in out.values() for b in v)
    print(f"{len(out)} papers with a known backbone -> {OUT}")
    for k, v in counts.most_common():
        print(f"  {v:4d} {k}")


if __name__ == "__main__":
    assert backbones("We fine-tune π0 with a SigLIP encoder. π0 and SigLIP again.\nReferences\nCLIP CLIP") == \
        ["SigLIP", "π0 / π0.5"]
    assert backbones("Grounding DINO boxes; Grounding DINO again") == ["Grounding DINO"]
    main()
