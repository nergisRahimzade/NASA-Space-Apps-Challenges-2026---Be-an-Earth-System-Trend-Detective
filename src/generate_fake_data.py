import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def make_fake_series(
    years: int = 20, 
    trend_slope: float = 0.05, 
    seasonal_amplitude: float = 2.5, 
    noise_level: float = 0.8,
    base_value: float = 14.0,
    seed: int = 42
) -> pd.DataFrame:
    """
    Generates a synthetic climate time-series combining a linear trend,
    a monthly seasonal cycle, and random Gaussian noise.
    """
    np.random.seed(seed)
    
    # Generate monthly timeline
    total_months = years * 12
    date_range = pd.date_range(start="2006-01-01", periods=total_months, freq="ME")
    
    # 1. Linear Trend component
    time_indices = np.arange(total_months)
    trend_component = trend_slope * time_indices
    
    # 2. Seasonal component (Sine wave tracking months)
    months = date_range.month
    # Shift sine wave so peak aligns realistically with summer months
    seasonal_component = seasonal_amplitude * np.sin(2 * np.pi * (months - 4) / 12)
    
    # 3. Random Noise component
    noise_component = np.random.normal(0, noise_level, total_months)
    
    # Combine signals into the final physical variable (e.g., Temperature)
    values = base_value + trend_component + seasonal_component + noise_component
    
    # Construct DataFrame aligning with expected schema contracts
    df = pd.DataFrame({
        "time": date_range,
        "raw_value": values
    })
    
    return df

def main():
    # Define repository paths relative to project root
    output_dir = "data"
    output_file = os.path.join(output_dir, "fake_series.csv")
    plot_file = os.path.join(output_dir, "fake_series_plot.png")
    
    # Ensure local directory structure exists
    os.makedirs(output_dir, exist_ok=True)
    
    print("Generating simulated 20-year monthly time-series...")
    df = make_fake_series(years=20, trend_slope=0.04, seasonal_amplitude=3.0, noise_level=0.7)
    
    # Save CSV artifact
    df.to_csv(output_file, index=False)
    print(f"✔ Successfully saved dataset artifact to: {output_file}")
    
    # Generate diagnostic verification plot
    plt.figure(figsize=(12, 5))
    plt.plot(df["time"], df["raw_value"], label="Simulated Monthly Variable", color="#2b5c8f", alpha=0.8)
    
    # Overlay an idealized trendline for baseline verification
    z = np.polyfit(np.arange(len(df)), df["raw_value"], 1)
    p = np.poly1d(z)
    plt.plot(df["time"], p(np.arange(len(df))), "r--", label=f"Estimated Linear Trend (slope={z[0]:.4f})", alpha=0.9)
    
    plt.title("Earth System Trend Detective - Simulated Verification Baseline", fontsize=12, fontweight="bold")
    plt.xlabel("Timeline (Years)")
    plt.ylabel("Value (Physical Units)")
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="upper left")
    plt.tight_layout()
    
    # Save plot visual
    plt.savefig(plot_file, dpi=150)
    plt.close()
    print(f"✔ Successfully saved trend visualization to: {plot_file}")

if __name__ == "__main__":
    main()

