"""Open a GeoTIFF, print its metadata, and display the image."""

import sys

import numpy as np
import rasterio

# Default to the Sentinel-2 optical GeoTIFF fetched by Tool_1, override via CLI arg.
DEFAULT_TIFF_PATH = (
    "Tools/Tool_1_fetch_satellite_imagery/sih_satellite_data/"
    "sentinel2_S2C_MSIL2A_20250128T053131_N0511_R105_T43RGM_20250128T084454_"
    "2025-01-01_2025-01-31_optical_20260902T180322Z.tif"
)


def show_metadata(dataset: rasterio.DatasetReader) -> None:
    print(f"File:        {dataset.name}")
    print(f"Driver:      {dataset.driver}")
    print(f"Size:        {dataset.width} x {dataset.height} (W x H)")
    print(f"Band count:  {dataset.count}")
    print(f"Dtypes:      {dataset.dtypes}")
    print(f"CRS:         {dataset.crs}")
    print(f"Transform:   {dataset.transform}")
    print(f"Bounds:      {dataset.bounds}")
    print(f"Nodata:      {dataset.nodata}")
    if dataset.tags():
        print(f"Tags:        {dataset.tags()}")
    for i, desc in enumerate(dataset.descriptions, start=1):
        if desc:
            print(f"  Band {i} description: {desc}")


def show_image(dataset: rasterio.DatasetReader) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("\nmatplotlib is not installed, skipping image display.")
        print("Install it with: pip install matplotlib")
        return

    band_count = dataset.count

    if band_count >= 3:
        # Assume the first three bands are R, G, B (or similar) for a quick-look composite.
        rgb = dataset.read([1, 2, 3]).astype(np.float32)
        for i in range(3):
            band = rgb[i]
            lo, hi = np.nanpercentile(band, (2, 98))
            rgb[i] = np.clip((band - lo) / (hi - lo + 1e-6), 0, 1)
        image = np.transpose(rgb, (1, 2, 0))
        plt.imshow(image)
        plt.title("Bands 1-3 as RGB composite (2-98 percentile stretch)")
    else:
        band = dataset.read(1)
        plt.imshow(band, cmap="gray")
        plt.title("Band 1")
        plt.colorbar(label="Pixel value")

    plt.xlabel("Column")
    plt.ylabel("Row")
    plt.tight_layout()
    plt.show()


def main() -> None:
    tiff_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TIFF_PATH

    with rasterio.open(tiff_path) as dataset:
        show_metadata(dataset)
        show_image(dataset)


if __name__ == "__main__":
    main()
