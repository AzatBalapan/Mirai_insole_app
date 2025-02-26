import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import SpanSelector

# Load sensor data
file_path = "recordings/male_with_autistic _desorder/PA1PA1S35H150W40M_Combined.csv"
df = pd.read_csv(file_path)

# Define left and right sensor columns
sensor_pairs = {
    "Left_Heel": "Right_Heel",
    "Left_Middle": "Right_Middle",
    "Left_Top": "Right_Top"
}

# Generate sequential indices for x-axis
time = range(len(df))

# Create subplots (2 columns, 3 rows)
fig, axs = plt.subplots(3, 2, figsize=(12, 9), sharex=True, sharey=True)
fig.suptitle('Sensor Data with Linked Zoom')

lines = []

for i, (left, right) in enumerate(sensor_pairs.items()):
    axs[i, 0].plot(time, df[left], label=f'{left}', linestyle='-', marker='.')
    axs[i, 1].plot(time, df[right], label=f'{right}', linestyle='-', marker='.')

    axs[i, 0].set_ylabel(left)
    axs[i, 1].set_ylabel(right)
    axs[i, 0].legend()
    axs[i, 1].legend()
    axs[i, 0].grid()
    axs[i, 1].grid()
    lines.append(axs[i, 0])
    lines.append(axs[i, 1])

axs[-1, 0].set_xlabel("Sample Index")
axs[-1, 1].set_xlabel("Sample Index")
axs[0, 0].set_title("Left Sensors")
axs[0, 1].set_title("Right Sensors")


# Function to update zoom for all subplots
def onselect(xmin, xmax):
    for ax in lines:
        ax.set_xlim(xmin, xmax)
    fig.canvas.draw()


# Add interactive zoom using SpanSelector
span_selectors = [SpanSelector(ax, onselect, 'horizontal', useblit=True) for ax in lines]

plt.tight_layout()
plt.show()
