import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import SpanSelector

# Load sensor data
file_path = "recordings/male with autistic desorder/PA1PA1S35H150W40M_Combined.csv"
df = pd.read_csv(file_path)

# Define left and right sensor columns
sensor_pairs = {
    "Left_Heel": "Right_Heel",
    "Left_Middle": "Right_Middle",
    "Left_Top": "Right_Top"
}

# Generate sequential indices for x-axis
time = range(len(df))

fig, axes = plt.subplots(3, 1, figsize=(12, 6), sharex=True)
fig.suptitle('Sensor Data with Linked Zoom')

lines = []

for i, (left, right) in enumerate(sensor_pairs.items()):
    ax = axes[i]

    line1, = ax.plot(time, df[left], label=f'{left}', color='b')
    line2, = ax.plot(time, df[right], label=f'{right}', color='r')

    ax.legend()
    lines.append(ax)


def onselect(xmin, xmax):
    for ax in lines:
        ax.set_xlim(xmin, xmax)
    fig.canvas.draw()


span_selectors = [SpanSelector(ax, onselect, 'horizontal', useblit=True) for ax in lines]

plt.tight_layout()
plt.show()
