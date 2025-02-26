import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import RectangleSelector

# File paths (update these as needed)
file1_path = "recordings/male with autistic desorder/patient1pat1_26_02_S36_H165_W56_M_Dev1.csv"
file2_path = "recordings/male with autistic desorder/patient1pat1_26_02_S36_H165_W56_M_Dev2.csv"

# Load data
df1 = pd.read_csv(file1_path)
df2 = pd.read_csv(file2_path)

# Extract relevant data (sequential indexing instead of timestamp)
sensors = ['sensor1', 'sensor2', 'sensor3', 'sensor4']
index1 = range(len(df1))
index2 = range(len(df2))

# Create subplots
fig, axs = plt.subplots(4, 1, figsize=(10, 12), sharex=True)

# Plot sensor data
lines = []
for i, sensor in enumerate(sensors):
    line1, = axs[i].plot(index1, df1[sensor], label=f'Left - {sensor}', linestyle='-', marker='.')
    line2, = axs[i].plot(index2, df2[sensor], label=f'Right - {sensor}', linestyle='-', marker='.')
    axs[i].set_ylabel(sensor)
    axs[i].legend()
    axs[i].grid()
    lines.append((line1, line2))

axs[-1].set_xlabel("Sample Index")
plt.suptitle("Sensor Data from Two Devices (Sequential Plot)")


# Function to update zoom for all subplots
def on_zoom(eclick, erelease):
    """Zoom synchronously on all subplots."""
    x_min, y_min = eclick.xdata, eclick.ydata
    x_max, y_max = erelease.xdata, erelease.ydata

    if None in [x_min, y_min, x_max, y_max]:  # Avoid errors on invalid selections
        return

    for ax in axs:
        ax.set_xlim(x_min, x_max)

    plt.draw()


# Add interactive zoom using RectangleSelector
selector = RectangleSelector(axs[0], on_zoom, interactive=True)

plt.show()
