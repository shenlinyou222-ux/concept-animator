"""Manim CE scenes for concept_animator nodes. Render: manim -ql manim_scene.py SectionSigma"""
from manim import *
import numpy as np


class SectionSigma(ThreeDScene):
    """σ(x,y,z) = x + 16(y + 16z): 3D 格子 -> 1D 偏移 的双射动画"""

    def construct(self):
        title = Text("Section: 16³ 体素段", font_size=34, color=WHITE).to_edge(UP)
        cube = Cube(side_length=2.2, fill_opacity=0.12, stroke_width=1.5, fill_color=BLUE)
        cube.set_stroke(BLUE_D)
        

        # 3D: pick one voxel
        self.add(title)
        self.set_camera_orientation(phi=65 * DEGREES, theta=-45 * DEGREES)
        self.play(Create(cube), run_time=1.2)
        self.begin_ambient_camera_rotation(rate=0.25)

        voxel = Cube(side_length=0.36, fill_opacity=0.95, fill_color=ORANGE)
        voxel.move_to(cube.get_center() + np.array([0.5, 0.3, -0.7]))
        coord = Text("(x,y,z) = (3, 7, 12)", font_size=28, color=ORANGE)
        coord.to_corner(DL)
        self.play(FadeIn(voxel), Write(coord), run_time=1.0)
        self.wait(1.0)

        # flatten to 1D strip
        formula = MathTex(r"\sigma(x,y,z) = x + 16\,(y + 16\,z)", font_size=44)
        formula.to_corner(DR)
        result = MathTex(r"\sigma(3,7,12) = 3 + 16\cdot 199 = 3187", font_size=38, color=YELLOW)
        result.next_to(formula, DOWN)
        self.play(Write(formula), run_time=1.2)
        self.play(Write(result), run_time=1.0)
        self.wait(1.2)

        # linear memory strip
        self.stop_ambient_camera_rotation()
        self.move_camera(phi=0, theta=-90 * DEGREES, run_time=1.0)
        strip = Rectangle(width=10, height=0.5, stroke_color=GREY_B, fill_color=GREY_D, fill_opacity=0.4)
        strip.to_edge(DOWN, buff=1.2)
        mark = Line(strip.get_left() + RIGHT * (10 * 3187 / 4096), strip.get_bottom() + UP * 0.3,
                    color=ORANGE, stroke_width=6)
        label = Text("偏移 3187 / 4096 字节", font_size=24, color=ORANGE).next_to(strip, UP)
        self.play(FadeOut(voxel), FadeOut(cube), Create(strip), FadeIn(label), GrowFromPoint(mark, strip.get_left()), run_time=1.5)
        self.wait(1.5)
        note = Text("坐标不占存储：由 σ 现场计算", font_size=26, color=BLUE_B).next_to(strip, DOWN, buff=0.4)
        self.play(Write(note))
        self.wait(2.0)


class LoadFactor(Scene):
    """α = n/m, E[探测] ≈ 1/(1−α): 曲线发散动画"""

    def construct(self):
        title = Text("哈希表装载因子 α = n/m", font_size=34).to_edge(UP)
        axes = Axes(x_range=[0, 1, 0.25], y_range=[0, 10, 2],
                    x_length=9, y_length=5,
                    axis_config={"include_numbers": True, "font_size": 22}).shift(DOWN * 0.6)
        x_lab = Text("α", font_size=26).next_to(axes.x_axis.get_end(), UP)
        y_lab = Text("E[探测]", font_size=26).rotate(90 * DEGREES).next_to(axes.y_axis.get_end(), RIGHT)

        curve = axes.plot(lambda x: min(1 / (1 - x), 10) if x < 0.97 else 10,
                          x_range=[0, 0.97], color=ORANGE, stroke_width=5)
        curve_label = Text("1/(1−α)", font_size=28, color=ORANGE).next_to(curve, RIGHT).shift(UP * 1.5 + LEFT * 0.7)

        danger_zone = Rectangle(width=0.9, height=5, fill_color=RED, fill_opacity=0.12, stroke_width=0)
        danger_zone.move_to(axes.c2p(0.925, 2.5))
        dz_label = Text("危险区 α>0.85", font_size=22, color=RED).move_to(axes.c2p(0.75, 8.8))

        marker_line = DashedLine(axes.c2p(0.7, 0), axes.c2p(0.7, 3.4), color=BLUE)
        marker_label = Text("扩容阈值 α₀ ≈ 0.7", font_size=24, color=BLUE).next_to(marker_line, UP).align_to(axes.c2p(0, 3.6), LEFT).shift(RIGHT * 2.4)

        self.add(title)
        self.play(Create(axes), Write(x_lab), Write(y_lab), run_time=1.2)
        self.play(Create(curve), run_time=2.0)
        self.play(Write(curve_label))
        self.play(FadeIn(danger_zone), Write(dz_label))
        self.play(Create(marker_line), Write(marker_label))
        self.wait(0.8)
        self.play(Indicate(curve, scale_factor=1.05), run_time=1.2)
        self.wait(2.0)
