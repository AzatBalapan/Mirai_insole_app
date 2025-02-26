import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import RectangleSelector

# File paths (update these as needed)
file1_path = "recordings/male_with_autistic _desorder/patient1pat1_26_02_S36_H165_W56_M_Dev1.csv"
file2_path = "recordings/male_with_autistic _desorder/patient1pat1_26_02_S36_H165_W56_M_Dev2.csv"

# Load data
df1 = pd.read_csv(file1_path)
df2 = pd.read_csv(file2_path)

# Extract relevant data (sequential indexing instead of timestamp)
sensors = ['sensor1', 'sensor2', 'sensor3', 'sensor4']
index1 = range(len(df1))
index2 = range(len(df2))

# Create subplots (2 columns, 4 rows)
fig, axs = plt.subplots(4, 2, figsize=(12, 12), sharex=True, sharey=True)

# Plot sensor data
for i, sensor in enumerate(sensors):
    axs[i, 0].plot(index1, df1[sensor], label=f'Left - {sensor}', linestyle='-', marker='.')
    axs[i, 1].plot(index2, df2[sensor], label=f'Right - {sensor}', linestyle='-', marker='.')

    axs[i, 0].set_ylabel(sensor)
    axs[i, 0].legend()
    axs[i, 1].legend()
    axs[i, 0].grid()
    axs[i, 1].grid()

axs[-1, 0].set_xlabel("Sample Index")
axs[-1, 1].set_xlabel("Sample Index")
axs[0, 0].set_title("Device 1 (Left)")
axs[0, 1].set_title("Device 2 (Right)")
plt.suptitle("Sensor Data from Two Devices (Side-by-Side Comparison)")


# Function to update zoom for all subplots
def on_zoom(eclick, erelease):
    """Zoom synchronously on all subplots."""
    x_min, y_min = eclick.xdata, eclick.ydata
    x_max, y_max = erelease.xdata, erelease.ydata

    if None in [x_min, y_min, x_max, y_max]:  # Avoid errors on invalid selections
        return

    for ax_row in axs:
        for ax in ax_row:
            ax.set_xlim(x_min, x_max)
            ax.set_ylim(y_min, y_max)

    plt.draw()


# Add interactive zoom using RectangleSelector
selector = RectangleSelector(axs[0, 0], on_zoom, interactive=True, useblit=True)
selector = RectangleSelector(axs[0, 1], on_zoom, interactive=True, useblit=True)

plt.tight_layout()
plt.show()
