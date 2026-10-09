"""Manim CE scenes v2: 哈希探测 / MeshBuilder vs ray-march"""
from manim import *
import numpy as np


class HashProbe(Scene):
    """Map 哈希表：h(cx,cz) -> 桶 i，冲突沿探测序列前进"""

    def construct(self):
        title = Text("Map = (h, A)：键 (cx,cz) → 桶", font_size=32).to_edge(UP)
        m = 8
        slot_w, gap = 1.0, 0.15
        slots = VGroup()
        for i in range(m):
            r = Rectangle(width=slot_w, height=0.8, stroke_color=GREY_B, fill_color="#1a1a2e", fill_opacity=1)
            slots.add(r)
        slots.arrange(RIGHT, buff=gap).shift(DOWN * 0.2)
        labels = VGroup(*[Text(str(i), font_size=22, color=GREY_A).next_to(slots[i], UP, buff=0.15) for i in range(m)])
        self.add(title)
        self.play(LaggedStart(*[FadeIn(r, shift=DOWN * 0.3) for r in slots], lag_ratio=0.06),
                  LaggedStart(*[FadeIn(l) for l in labels], lag_ratio=0.06), run_time=1.4)

        key = Text("键 k₁ = (3, 7)", font_size=28, color=ORANGE).to_corner(UL).shift(DOWN * 0.9)
        formula = Text("h(3,7) = (3a+7b) mod 8 = 5", font_size=26, color=BLUE_B).next_to(key, DOWN, aligned_edge=LEFT)
        self.play(Write(key), Write(formula))

        arrow = Arrow(key.get_right() + RIGHT * 0.3, slots[5].get_top() + UP * 0.15, color=ORANGE, stroke_width=5)
        chip = Rectangle(width=0.8, height=0.5, fill_color=ORANGE, fill_opacity=1, stroke_width=0)
        chip_text = Text("k₁", font_size=24, color=BLACK)
        chipgrp = VGroup(chip, chip_text)
        self.play(GrowArrow(arrow))
        self.play(FadeIn(chipgrp.move_to(slots[5])))
        self.wait(0.6)

        key2 = Text("键 k₂ = (11, 2) → h = 5  冲突!", font_size=26, color=RED).next_to(formula, DOWN, aligned_edge=LEFT)
        ghost = Rectangle(width=0.8, height=0.5, stroke_color=RED, stroke_width=3).move_to(slots[5])
        self.play(Write(key2), Create(ghost))
        probe_arrow = Arrow(slots[5].get_bottom() + DOWN * 0.2, slots[6].get_bottom() + DOWN * 0.2,
                            color=RED, stroke_width=4).shift(DOWN * 0.25)
        ptxt = Text("开放寻址：探测下一格 i+1", font_size=22, color=RED).next_to(probe_arrow, DOWN, buff=0.15)
        chip2 = chipgrp.copy().set_opacity(1)
        self.play(GrowArrow(probe_arrow), Write(ptxt))
        self.play(chip2.animate.move_to(slots[6]))
        self.wait(0.5)

        note = Text("鸽笼原理：|ℤ²| > m ⟹ 冲突不可避免", font_size=26, color=YELLOW).to_edge(DOWN, buff=0.5)
        self.play(Write(note))
        self.wait(2.0)


class MeshVsRaymarch(Scene):
    """左：MeshBuilder 建网格再上传；右：ray-march 直接在张量上走射线"""

    def construct(self):
        title = Text("渲染范式对比：MeshBuilder vs ray-march", font_size=30).to_edge(UP)
        self.add(title)
        left_t = Text("CPU：先建 mesh", font_size=26, color=BLUE_B).shift(LEFT * 3.4 + UP * 1.6)
        right_t = Text("GPU：直接走射线", font_size=26, color=ORANGE).shift(RIGHT * 3.4 + UP * 1.6)

        # left: voxel grid -> extracted mesh -> upload
        cells = VGroup()
        n = 5
        for i in range(n):
            for j in range(n):
                if (i + j) % 2 == 0 or i == 2:
                    sq = Square(side_length=0.5, stroke_width=1, stroke_color=GREY_D).shift(
                        LEFT * 3.4 + UP * 0.1 + RIGHT * (i - 2) * 0.5 + DOWN * (j - 2) * 0.5)
                    cells.add(sq)
        mesh_frame = SurroundingRectangle(cells, color=BLUE, buff=0.2)
        mesh_label = Text("邻接测试→mesh→VAO 上传", font_size=20, color=BLUE_B).next_to(cells, DOWN, buff=0.5)
        self.play(Write(left_t), LaggedStart(*[Create(s) for s in cells], lag_ratio=0.02), run_time=1.6)
        self.play(Create(mesh_frame), Write(mesh_label))
        cost1 = Text("改 1 格 → 重建整段 0.01~5ms", font_size=20, color=RED).next_to(mesh_label, DOWN, buff=0.2)
        self.play(Write(cost1))

        # right: tensor + rays
        tensor = Rectangle(width=2.6, height=2.6, stroke_color=ORANGE, fill_color="#1f1405", fill_opacity=1
                           ).shift(RIGHT * 3.4 + UP * 0.1)
        t_label = Text("4KB 体素张量（唯一数据）", font_size=20, color=ORANGE).next_to(tensor, DOWN, buff=0.5)
        rays = VGroup()
        for k in range(5):
            a = tensor.get_left() + UP * (1.1 - 0.55 * k)
            d = RIGHT * 2.2 + RIGHT * (k - 2) * 0.06
            rays.add(Arrow(a, a + d, color=YELLOW, stroke_width=3, max_tip_length_to_length_ratio=0.08))
        self.play(Write(right_t), Create(tensor), Write(t_label))
        self.play(LaggedStart(*[GrowArrow(r) for r in rays], lag_ratio=0.15), run_time=1.6)
        cost2 = Text("无 mesh 无上传；只见可见体素", font_size=20, color=GREEN_B).next_to(t_label, DOWN, buff=0.2)
        self.play(Write(cost2))

        verdict = Text("MeshBuilder 整体删除 —— 范式更换，不是优化", font_size=26, color=YELLOW).to_edge(DOWN, buff=0.5)
        self.play(Write(verdict))
        self.wait(2.5)
