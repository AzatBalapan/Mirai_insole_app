import pandas as pd

def calculate_asymmetry(file_path):
    # Load the CSV file
    df = pd.read_csv(file_path)

    # Define left and right sensor columns
    sensor_pairs = {
        "Left_Heel": "Right_Heel",
        "Left_Middle": "Right_Middle",
        "Left_Top": "Right_Top"
    }

    # Compute the average values for each sensor
    avg_values = df.mean()

    # Compute asymmetry as (Left - Right) / max(Left, Right)
    asymmetry = {
        left: (avg_values[left] - avg_values[right]) / max(avg_values[left], avg_values[right])
        for left, right in sensor_pairs.items()
    }

    # Print results
    print("Sensor Asymmetry Report:")
    print("=" * 40)
    for left, right in sensor_pairs.items():
        print(f"{left} - {right}: {asymmetry[left]:.4f}")
    print("=" * 40)

if __name__ == "__main__":
    # Specify file path (update with correct file path before running)
    file_path = "recordings/tagir_13_02_3sensors/tagiryerzhS36H127W36M_Combined.csv"

    calculate_asymmetry(file_path)
