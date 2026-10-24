"""Find the robots each CoRL 2026 paper uses, by matching known platform names in the PDF text before References.

Writes htmls/corl2026/robots.json: {paper_id: [robot names]}; htmls/corl2026/build.py turns the top 50 into a filter.

    uv run python specific_scripts/corl2026_robots.py
"""

import collections
import glob
import json
import os
import re

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "htmls", "corl2026")
OUT = os.path.join(HERE, "robots.json")
MIN_MENTIONS = 2  # ponytail: one passing mention is usually related work; robots used in experiments recur
REFS_RE = re.compile(r"\n\s*(?:References|Bibliography)\s*\n")

# canonical name -> regex; ambiguous words (Spot, Stretch, Fetch, Digit, Inspire) need a robot-ish neighbour
ROBOTS = {
    "Franka (Panda / FR3)": r"\bFranka\b|\bFR3\b|\bPanda (?:arm|robot)",
    "Unitree G1": r"Unitree\s*G1\b|\bG1 humanoid",
    "Unitree H1": r"Unitree\s*H1\b|\bH1(?:-2)? humanoid",
    "Unitree Go2": r"Unitree\s*Go2\b|\bGo2\b",
    "Unitree Go1": r"Unitree\s*Go1\b|\bGo1\b",
    "Unitree A1": r"Unitree\s*A1\b",
    "Unitree B1 / B2": r"Unitree\s*B[12]\b",
    "Unitree Z1": r"Unitree\s*Z1\b",
    "Unitree Dex3 hand": r"\bDex3\b",
    "Boston Dynamics Spot": r"Boston Dynamics(?:'s|’s)? Spot|\bSpot (?:robot|quadruped|arm)",
    "Boston Dynamics Atlas": r"Boston Dynamics(?:'s|’s)? Atlas|\bAtlas humanoid",
    "ANYmal": r"\bANY[mM]al\b",
    "Agility Digit": r"Agility(?: Robotics)?(?:'s|’s)? Digit|\bDigit humanoid",
    "Cassie": r"\bCassie\b",
    "Booster T1": r"Booster\s*T1\b",
    "Fourier GR1": r"Fourier\s*GR-?[12]\b|\bGR-?1 humanoid",
    "Tiangong humanoid": r"Tian ?[Gg]ong",
    "Noetix E1": r"Noetix",
    "UR5 / UR5e": r"\bUR5e?\b",
    "UR10 / UR10e": r"\bUR10e?\b",
    "UR3 / UR3e": r"\bUR3e?\b",
    "UR7e": r"\bUR7e\b",
    "UFactory xArm": r"\bx[Aa]rm\s*\d*\b|UFactory",
    "UFactory Lite6": r"\bLite ?6\b",
    "Kinova (Gen3 / Jaco)": r"\bKinova\b|\bJaco\b",
    "KUKA iiwa": r"\bKUKA\b|\biiwa\b",
    "Rethink Sawyer": r"\bSawyer\b",
    "Rethink Baxter": r"\bBaxter\b",
    "WidowX": r"\bWidow-?X\b",
    "ViperX": r"\bViper-?X\b",
    "ALOHA / Mobile ALOHA": r"\bALOHA\b|\bAloha\b",
    "AgileX Piper": r"\bPi[Pp][Ee][Rr]\b",
    "AgileX Cobot Magic": r"Cobot Magic|COBOT MAGIC",
    "ARX arm": r"\bARX\b",
    "I2RT YAM": r"\bYAM\b",
    "Galaxea (R1 / A1X)": r"\bGalaxea\b",
    "Galbot G1": r"\bGalbot\s*G1\b",
    "AgiBot (G1 / A2)": r"\bAgi[Bb]ot\s*(?:G1|A2|X1)\b",
    "Astribot S1": r"\bAstribot\b",
    "RealMan arm": r"\bReal[Mm]an\b|\bRM(?:65|75)\b",
    "Flexiv Rizon": r"\bFlexiv\b|\bRizon\b",
    "ABB YuMi": r"\bYuMi\b",
    "Rainbow RB-Y1": r"\bRB-Y1\b",
    "Hello Robot Stretch": r"Hello Robot|\bStretch (?:robot|RE[12]|[23]\b)",
    "Fetch": r"\bFetch (?:robot|mobile)",
    "PAL TIAGo": r"\bTIAGo\b|\bTiago\b",
    "PR2": r"\bPR2\b",
    "Toyota HSR": r"\bHSR\b|Human Support Robot",
    "TurtleBot": r"\bTurtle[Bb]ot\b",
    "Clearpath Jackal / Husky": r"\bJackal\b|\bHusky\b",
    "Crazyflie": r"\bCrazyflie\b",
    "DJI drone": r"\bDJI\b",
    "da Vinci / dVRK": r"\bda Vinci\b|\bdVRK\b",
    "SO-100 / SO-101": r"\bSO-? ?10[01]\b",
    "Koch arm": r"\bKoch (?:v?1\.1|arm)",
    "AIRBOT Play": r"\bAIRBOT\b|\bAirbot\b",
    "Dobot": r"\bDobot\b",
    "LEAP Hand": r"\bLEAP\s*[Hh]and\b|\bLEAP\b",
    "Allegro Hand": r"\bAllegro\b",
    "Shadow Hand": r"\bShadow\s*(?:Dexterous\s*)?[Hh]and\b",
    "Inspire Hand": r"\bInspire (?:[Dd]exterous |RH56\w* )?[Hh]and\b|\bInspire RH56",
    "Ability Hand": r"\bAbility [Hh]and\b|\bPSYONIC\b",
    "XHand": r"\bX-?Hand\b",
    "Sharpa Wave hand": r"\bSharpa\b",
    "Wuji Hand": r"\bWUJI\b|\bWuji [Hh]and\b",
    "Barrett WAM / Hand": r"\bBarrett\b",  # bare "WAM" = world action model
    "ToddlerBot": r"\bToddlerBot\b",
    "Berkeley Humanoid": r"\bBerkeley Humanoid\b",
}
ROBOT_RES = {k: re.compile(v) for k, v in ROBOTS.items()}


def robots(text):
    text = REFS_RE.split(text)[0].replace("\n", " ")
    return [k for k, rx in ROBOT_RES.items() if len(rx.findall(text)) >= MIN_MENTIONS]


def main():
    out = {}
    for p in sorted(glob.glob(os.path.join(HERE, "pdfs", "*.pdf"))):
        with pymupdf.open(p) as doc:
            found = robots("\n".join(page.get_text() for page in doc))
        if found:
            out[os.path.basename(p).split("_", 1)[0]] = found
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    counts = collections.Counter(r for v in out.values() for r in v)
    print(f"{len(out)} papers with a known robot -> {OUT}")
    for k, v in counts.most_common():
        print(f"  {v:4d} {k}")


if __name__ == "__main__":
    assert robots("We use a Unitree G1. The G1 humanoid walks.\nReferences\nUnitree G1 G1 humanoid UR5 UR5") == ["Unitree G1"]
    assert robots("a Spot on the table, Spot check") == []
    main()
