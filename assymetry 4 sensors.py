import pandas as pd


def calculate_asymmetry(file1, file2):
    # Load the CSV files
    df1 = pd.read_csv(file1)
    df2 = pd.read_csv(file2)

    # Define sensor columns
    sensor_columns = [col for col in df1.columns if col.startswith("sensor")]

    # Compute the average values for each sensor in both datasets
    avg_dev1 = df1[sensor_columns].mean()
    avg_dev2 = df2[sensor_columns].mean()

    # Compute asymmetry for each sensor
    asymmetry = (avg_dev1 - avg_dev2) / avg_dev1.combine(avg_dev2, max)

    # Print results
    print("Sensor Asymmetry Report:")
    print("=" * 40)
    for sensor in sensor_columns:
        print(
            f"{sensor}: Average Dev1 = {avg_dev1[sensor]:.2f}, Average Dev2 = {avg_dev2[sensor]:.2f}, Asymmetry = {asymmetry[sensor]:.4f}")
    print("=" * 40)


if __name__ == "__main__":
    # Specify file paths (update with correct file paths before running)
    file1_path = "recordings/male with autistic desorder/patient1pat1_26_02_S36_H165_W56_M_Dev1.csv"
    file2_path = "recordings/male with autistic desorder/patient1pat1_26_02_S36_H165_W56_M_Dev2.csv"

    calculate_asymmetry(file1_path, file2_path)
