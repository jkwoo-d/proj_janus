import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import trackpy as tp

import config


def detect_particles(frames, diameter: int = None, min_mass: float = None) -> pd.DataFrame:
    diameter = diameter or config.PARTICLE_DIAMETER
    min_mass = min_mass or config.MIN_MASS

    tp.quiet()
    results = []
    for i, frame in enumerate(frames):
        f = tp.locate(frame, diameter=diameter, minmass=min_mass)
        if len(f):
            f['frame'] = i
            results.append(f)

    if not results:
        return pd.DataFrame()

    detected = pd.concat(results, ignore_index=True)
    print(f"  Detected {len(detected)} particle instances across {detected['frame'].nunique()} frames")
    return detected


def preview_detection(frame: np.ndarray, diameter: int = None, min_mass: float = None,
                      save_path: str = None) -> pd.DataFrame:
    diameter = diameter or config.PARTICLE_DIAMETER
    min_mass = min_mass or config.MIN_MASS

    f = tp.locate(frame, diameter=diameter, minmass=min_mass)
    print(f"  Found {len(f)} particles (diameter={diameter}, min_mass={min_mass})")

    fig, ax = plt.subplots(figsize=(10, 8))
    tp.annotate(f, frame, ax=ax, imshow_style={'cmap': 'gray'})
    ax.set_title(f"Preview: {len(f)} particles detected\n"
                 f"diameter={diameter}, min_mass={min_mass}")

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
    else:
        plt.show()

    return f
