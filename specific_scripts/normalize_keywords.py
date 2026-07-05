"""Normalize author keywords across ConferenceTables/*.csv.

Produces docs/keyword_normalization.tsv: one line per normalized keyword
that merges >= 2 distinct original spellings, sorted by total paper count:

    <canonical display>\t<total papers>\t<variant 1>\t<variant 2>...

Review/correct that file; applying it to the viewers is a separate step.
"""

import collections
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# token-level acronym/synonym expansions, applied after lowercasing/splitting
TOKEN_MAP = {
    "llm": "large language model",
    "llms": "large language models",
    "mllm": "multimodal large language model",
    "mllms": "multimodal large language models",
    "lm": "language model",
    "lms": "language models",
    "rl": "reinforcement learning",
    "drl": "deep reinforcement learning",
    "marl": "multi agent reinforcement learning",
    "irl": "inverse reinforcement learning",
    "rlhf": "reinforcement learning from human feedback",
    "gnn": "graph neural network",
    "gnns": "graph neural networks",
    "cnn": "convolutional neural network",
    "cnns": "convolutional neural networks",
    "nlp": "natural language processing",
    "vlm": "vision language model",
    "vlms": "vision language models",
    "vla": "vision language action",
    "vlas": "vision language actions",
    "gan": "generative adversarial network",
    "gans": "generative adversarial networks",
    "vae": "variational autoencoder",
    "vaes": "variational autoencoders",
    "ood": "out of distribution",
    "xai": "explainable artificial intelligence",
    "dl": "deep learning",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "nn": "neural network",
    "nns": "neural networks",
    "kg": "knowledge graph",
    "kgs": "knowledge graphs",
    "multiagent": "multi agent",
    "multimodal": "multi modal",
    "multitask": "multi task",
}

KEEP_S = ("ss", "us", "is", "ics", "series", "bias", "atlas", "canvas", "bayes")


def singular(word):
    """Naive depluralization. ponytail: last-word heuristics, not a lemmatizer."""
    if len(word) <= 3 or word.endswith(KEEP_S):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("es") and word[-3] in "xhs":  # boxes, patches, classes
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def normalize(kw):
    s = kw.lower().strip()
    s = re.sub(r"[-_/]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    tokens = []
    for t in s.split(" "):
        tokens.extend(TOKEN_MAP.get(t, t).split(" "))
    tokens = [singular(t) for t in tokens if t]
    return " ".join(tokens)


def load_keyword_counts():
    """Return Counter of original keyword spellings -> number of papers."""
    counts = collections.Counter()
    for path in glob.glob(os.path.join(ROOT, "ConferenceTables", "*.csv")):
        for line in open(path):
            cols = line.rstrip("\n").split("\t")
            kw = cols[3] if len(cols) == 11 else (cols[2] if len(cols) >= 9 else "")
            seen = set()
            for k in kw.split(";"):
                k = k.strip()
                if k and k not in seen:
                    seen.add(k)
                    counts[k] += 1
    return counts


def build_groups(counts):
    """Map normalized form -> list of (original, count), canonical display first."""
    groups = collections.defaultdict(list)
    for orig, n in counts.items():
        norm = normalize(orig)
        if norm:
            groups[norm].append((orig, n))
    for variants in groups.values():
        variants.sort(key=lambda x: -x[1])
    return groups


def main():
    counts = load_keyword_counts()
    groups = build_groups(counts)
    merged = {norm: v for norm, v in groups.items() if len(v) >= 2}
    out = os.path.join(ROOT, "docs", "keyword_normalization.tsv")
    with open(out, "w") as f:
        f.write("# canonical\ttotal_papers\tvariants (original spelling: papers)\n")
        for norm, variants in sorted(merged.items(), key=lambda x: -sum(n for _, n in x[1])):
            total = sum(n for _, n in variants)
            display = variants[0][0]
            f.write(f"{display}\t{total}\t" + "\t".join(f"{o}: {n}" for o, n in variants) + "\n")
    print(f"{len(counts)} original keywords -> {len(groups)} normalized")
    print(f"{len(merged)} normalized keywords merge >=2 spellings -> {out}")


if __name__ == "__main__":
    main()
