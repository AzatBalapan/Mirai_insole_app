import pygame
import math

# Pygame initialization
pygame.init()
SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
clock = pygame.time.Clock()

# Define stick figure parameters
torso_length = 100
thigh_length = 80
leg_length = 80
foot_length = 60  # Length between heel and toe (longest side)
foot_height = 20  # Height from the ground to the ankle
hip_x, hip_y = 400, 300  # Hip joint position
shoulder_x, shoulder_y = hip_x, hip_y - torso_length  # Shoulder position
head_radius = 30  # Head size

# Joint angles (in radians)
angles = {
    "β16": math.pi / 6,  # Hip to thigh
    "β13": -math.pi / 4,  # Thigh to leg
    "β34": math.pi / 8,  # Leg to ankle
}

# Walking animation parameters
step_speed = 0.05
foot_roll_phase = 0.2  # Fraction of the step duration spent rolling
foot_roll_offset = 10  # Vertical adjustment during rolling

# Ground level
ground_y = 450

# Colors for different body parts
colors = {
    "left_leg": (0, 0, 200),  # Darker blue for the left leg
    "right_leg": (0, 0, 255),  # Lighter blue for the right leg
    "torso": (100, 100, 100),  # Gray torso
    "head": (200, 150, 100),  # Skin tone head
}

def draw_rotated_ellipse_with_pivots(surface, color, start, end, width):
    """
    Draw an ellipse rotated between two points such that its edges align with the pivot points.
    """
    center_x = (start[0] + end[0]) / 2
    center_y = (start[1] + end[1]) / 2

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    angle = math.atan2(dy, dx)
    length = math.sqrt(dx**2 + dy**2)

    ellipse_rect = pygame.Rect(0, 0, length, width)
    ellipse_rect.center = (center_x, center_y)

    ellipse_surface = pygame.Surface(ellipse_rect.size, pygame.SRCALPHA)
    pygame.draw.ellipse(ellipse_surface, color, (0, 0, *ellipse_rect.size))
    rotated_surface = pygame.transform.rotate(ellipse_surface, math.degrees(-angle))
    new_rect = rotated_surface.get_rect(center=ellipse_rect.center)
    surface.blit(rotated_surface, new_rect)

def calculate_joint_positions(current_time, side):
    """
    Calculate joint positions for the left or right leg based on angles and lengths.
    """
    phase_offset = math.pi if side == "left" else 0

    hip_angle = angles["β16"] * math.sin(current_time + phase_offset)
    knee_angle = angles["β13"] * math.sin(current_time + math.pi / 2 + phase_offset)
    ankle_angle = angles["β34"] * math.sin(current_time + phase_offset)

    knee_x = hip_x + thigh_length * math.sin(hip_angle)
    knee_y = hip_y + thigh_length * math.cos(hip_angle)

    ankle_x = knee_x + leg_length * math.sin(hip_angle + knee_angle)
    ankle_y = knee_y + leg_length * math.cos(hip_angle + knee_angle)

    foot_angle = hip_angle + knee_angle + ankle_angle
    foot_dx = foot_length * math.cos(foot_angle)
    foot_dy = foot_length * math.sin(foot_angle)
    foot_start = (ankle_x, ankle_y)
    foot_end = (ankle_x + foot_dx, ankle_y + foot_dy)

    roll_fraction = ((current_time + phase_offset) % (2 * math.pi)) / (2 * math.pi)
    if roll_fraction < foot_roll_phase:
        roll_adjustment = foot_roll_offset * (1 - roll_fraction / foot_roll_phase)
        foot_start = (foot_start[0], min(foot_start[1] - roll_adjustment, ground_y))
        foot_end = (foot_end[0], min(foot_end[1] - roll_adjustment, ground_y))

    return {
        "knee": (knee_x, knee_y),
        "ankle": (ankle_x, ankle_y),
        "foot": (foot_start, foot_end),
    }

def draw_leg(joints, color):
    """
    Draw a single leg based on the joint positions and color.
    """
    draw_rotated_ellipse_with_pivots(screen, color, (hip_x, hip_y), joints["knee"], 20)
    pygame.draw.circle(screen, (255, 0, 0), (hip_x, hip_y), 5)  # Hip pivot

    draw_rotated_ellipse_with_pivots(screen, color, joints["knee"], joints["ankle"], 15)
    pygame.draw.circle(screen, (0, 255, 0), (int(joints["knee"][0]), int(joints["knee"][1])), 5)  # Knee pivot

    draw_rotated_ellipse_with_pivots(screen, color, joints["foot"][0], joints["foot"][1], foot_height)
    pygame.draw.circle(screen, (0, 0, 255), (int(joints["ankle"][0]), int(joints["ankle"][1])), 5)  # Ankle pivot

def draw_torso():
    """
    Draw the torso as an ellipse between the hip and shoulder.
    Returns the dynamic shoulder position.
    """
    shoulder_x_offset = 10 * math.sin(current_time)  # Slight horizontal shoulder movement
    shoulder_y_offset = 5 * math.cos(current_time)  # Slight vertical shoulder movement
    shoulder_position = (shoulder_x + shoulder_x_offset, shoulder_y + shoulder_y_offset)

    draw_rotated_ellipse_with_pivots(screen, colors["torso"], (hip_x, hip_y), shoulder_position, 25)
    pygame.draw.circle(screen, (255, 0, 0), (hip_x, hip_y), 5)  # Hip pivot
    pygame.draw.circle(screen, (0, 255, 0), (int(shoulder_position[0]), int(shoulder_position[1])), 5)  # Shoulder pivot

    return shoulder_position  # Return shoulder position for head placement
def draw_head(shoulder_position):
    """
    Draw the head as a circle directly above the shoulders.
    """
    head_x = shoulder_position[0]
    head_y = shoulder_position[1] - head_radius - 5  # Positioned right above shoulders

    pygame.draw.circle(screen, colors["head"], (int(head_x), int(head_y)), head_radius)

def draw_stick_figure(current_time):
    """
    Draw the entire stick figure with both legs, torso, and head.
    """
    right_joints = calculate_joint_positions(current_time, "right")
    left_joints = calculate_joint_positions(current_time, "left")

    draw_leg(right_joints, colors["right_leg"])
    draw_leg(left_joints, colors["left_leg"])

    shoulder_position = draw_torso()  # Get shoulder position
    draw_head(shoulder_position)  # Pass shoulder position to head function

    pygame.draw.line(screen, (0, 0, 0), (0, ground_y), (SCREEN_WIDTH, ground_y), 2)

# Main loop
running = True
current_time = 0
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    screen.fill((255, 255, 255))

    current_time += step_speed
    angles["β16"] = math.pi / 6 * math.sin(current_time)
    angles["β13"] = -math.pi / 4 * math.sin(current_time + math.pi / 2)
    angles["β34"] = math.pi / 8 * math.sin(current_time)

    draw_stick_figure(current_time)
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
