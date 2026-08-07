import os
import numpy as np
import pandas as pd

import config


def compute_ensemble_stats(fit_results: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not fit_results:
        return pd.DataFrame(), pd.DataFrame()

    per_particle = pd.DataFrame(
        [{'particle': pid, **vals} for pid, vals in fit_results.items()]
    )

    D = per_particle['D']
    alpha = per_particle['alpha']
    unit = 'µm²/s' if config.PIXEL_SIZE_NM else 'px²/s'

    row = {
        'n_particles': len(per_particle),
        f'D_mean_{unit}': D.mean(),
        f'D_median_{unit}': D.median(),
        f'D_std_{unit}': D.std(),
        f'D_p25_{unit}': D.quantile(0.25),
        f'D_p75_{unit}': D.quantile(0.75),
        'alpha_mean': alpha.mean(),
        'alpha_median': alpha.median(),
        'alpha_std': alpha.std(),
    }

    for mtype in ['brownian', 'confined', 'directed']:
        count = int((per_particle['motion_type'] == mtype).sum())
        row[f'n_{mtype}'] = count
        row[f'pct_{mtype}'] = round(100.0 * count / len(per_particle), 1)

    return pd.DataFrame([row]), per_particle


def save_results(ensemble_stats: pd.DataFrame, per_particle: pd.DataFrame):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    ensemble_stats.to_csv(f"{config.OUTPUT_DIR}/ensemble_stats.csv", index=False)
    per_particle.to_csv(f"{config.OUTPUT_DIR}/per_particle_results.csv", index=False)
    print(f"  CSVs saved → {config.OUTPUT_DIR}/")
