"""Write plan.json: the seeded order of models and depths for every round. Deterministic."""
import json
import pathlib
import random

SEED = 20261012
DEPTHS = [64, 4096, 16384, 32768]
ROUNDS = 3
HERE = pathlib.Path(__file__).parent


def make_plan(seed: int = SEED, rounds: int = ROUNDS) -> dict:
    models = list(json.loads((HERE / "models.json").read_text()))
    rng = random.Random(seed)
    plan = {"seed": seed, "depths": DEPTHS, "rounds": []}
    for r in range(rounds):
        order = models[:]
        rng.shuffle(order)
        blocks = []
        for m in order:
            d = DEPTHS[:]
            rng.shuffle(d)
            blocks.append({"model": m, "depths": d})
        plan["rounds"].append({"round": r + 1, "blocks": blocks})
    return plan


BACKENDS = ["vulkan", "rocm"]


def make_paired_plan(seed: int, rounds: int = ROUNDS) -> dict:
    """Both backends in one session: in every round each model is run on both, the backend order and the
    depth order being seeded shuffles, so drift in the room or the machine hits both backends alike."""
    models = list(json.loads((HERE / "models.json").read_text()))
    rng = random.Random(seed)
    plan = {"seed": seed, "depths": DEPTHS, "backends": BACKENDS, "rounds": []}
    for r in range(rounds):
        order = models[:]
        rng.shuffle(order)
        blocks = []
        for m in order:
            be = BACKENDS[:]
            rng.shuffle(be)
            for b in be:
                d = DEPTHS[:]
                rng.shuffle(d)
                blocks.append({"model": m, "backend": b, "depths": d})
        plan["rounds"].append({"round": r + 1, "blocks": blocks})
    return plan


if __name__ == "__main__":
    import sys
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else SEED
    out = HERE / (sys.argv[2] if len(sys.argv) > 2 else "plan.json")
    paired = len(sys.argv) > 3 and sys.argv[3] == "paired"
    out.write_text(json.dumps(make_paired_plan(seed) if paired else make_plan(seed), indent=1) + "\n")
    print("wrote", out)
