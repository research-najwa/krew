#!/usr/bin/env python3
"""Generate Krew Investor Pitch Deck as PowerPoint (.pptx)"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
import os

# ─── COLORS ───
ACCENT = RGBColor(0x4F, 0x46, 0xE5)   # indigo
ACCENT2 = RGBColor(0x63, 0x66, 0xF1)
TEXT = RGBColor(0x1A, 0x1A, 0x1A)
TEXT2 = RGBColor(0x6B, 0x72, 0x80)
TEXT3 = RGBColor(0x9C, 0xA3, 0xAF)
BG = RGBColor(0xFA, 0xFA, 0xFA)
SURFACE = RGBColor(0xFF, 0xFF, 0xFF)
BORDER = RGBColor(0xE5, 0xE5, 0xE5)
RED = RGBColor(0xDC, 0x26, 0x26)
GREEN = RGBColor(0x16, 0xA3, 0x4A)
BLUE = RGBColor(0x25, 0x63, 0xEB)
PINK = RGBColor(0xDB, 0x27, 0x77)
ORANGE = RGBColor(0xEA, 0x58, 0x0C)
PURPLE = RGBColor(0x7C, 0x3A, 0xED)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# Agent colors
AGENT_COLORS = {
    'Deema': ACCENT, 'Waleed': BLUE, 'Mohammad': GREEN,
    'Yara': PINK, 'Norah': ORANGE, 'Sarah': PURPLE
}

AGENT_BG = {
    'Deema': RGBColor(0xEE, 0xEF, 0xFC), 'Waleed': RGBColor(0xDB, 0xEA, 0xFE),
    'Mohammad': RGBColor(0xDC, 0xFC, 0xE7), 'Yara': RGBColor(0xFC, 0xE7, 0xF3),
    'Norah': RGBColor(0xFF, 0xED, 0xD5), 'Sarah': RGBColor(0xF3, 0xE8, 0xFF)
}

AGENTS = [
    ('Deema', 'D', 'Employee Services', 'Answers employee questions instantly — PTO, benefits, policies. Via WhatsApp, Slack, or email. 24/7.'),
    ('Waleed', 'W', 'Onboarding', 'Guides every new hire from offer letter to day 90. Personalized checklists, buddy matching, check-ins.'),
    ('Mohammad', 'M', 'Recruitment', 'Screens resumes, ranks candidates, schedules interviews. Handles 80% of the hiring pipeline.'),
    ('Yara', 'Y', 'Compliance', 'Monitors regulations, drafts policy updates, runs compliance audits, tracks training completion.'),
    ('Norah', 'N', 'Finance & Analytics', 'Tracks headcount budgets, forecasts workforce costs, flags overspending, benchmarks compensation.'),
    ('Sarah', 'S', 'Agent Factory', 'Analyzes any job description and tells you: human or virtual employee? Our secret weapon.'),
]

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
W = prs.slide_width
H = prs.slide_height

def add_bg(slide):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = BG

def add_text(slide, left, top, width, height, text, font_size=18, bold=False, color=TEXT, alignment=PP_ALIGN.LEFT, font_name='Calibri'):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = font_name
    p.alignment = alignment
    return txBox

def add_section_label(slide, left, top, text):
    return add_text(slide, left, top, Inches(4), Inches(0.4), text, font_size=11, bold=True, color=ACCENT)

def add_title(slide, left, top, text, width=Inches(10)):
    return add_text(slide, left, top, width, Inches(0.8), text, font_size=36, bold=True, color=TEXT)

def add_subtitle(slide, left, top, text, width=Inches(9)):
    return add_text(slide, left, top, width, Inches(0.6), text, font_size=16, color=TEXT2)

def add_rounded_rect(slide, left, top, width, height, fill_color=SURFACE, border_color=BORDER):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.color.rgb = border_color
    shape.line.width = Pt(1)
    shape.adjustments[0] = 0.05
    return shape

def add_avatar_circle(slide, left, top, size, letter, bg_color, text_color):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, size, size)
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg_color
    shape.line.fill.background()
    tf = shape.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.text = letter
    p.font.size = Pt(int(size / Inches(1) * 14))
    p.font.bold = True
    p.font.color.rgb = text_color
    p.font.name = 'Calibri'
    p.alignment = PP_ALIGN.CENTER
    tf.paragraphs[0].space_before = Pt(0)
    tf.paragraphs[0].space_after = Pt(0)
    shape.text_frame.auto_size = None
    return shape


# ═══════════════════════════════════════════════
# SLIDE 1: TITLE
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
add_bg(slide)

add_text(slide, Inches(0), Inches(1.2), W, Inches(0.6), 'Krew', font_size=28, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(0), Inches(1.9), W, Inches(1.0), 'Your AI HR Department', font_size=48, bold=True, color=TEXT, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(0), Inches(2.9), W, Inches(0.5), '18 virtual employees. 5 divisions. One subscription.', font_size=20, color=TEXT2, alignment=PP_ALIGN.CENTER)

# Agent avatars row
avatar_size = Inches(0.55)
start_x = Inches(4.7)
y = Inches(3.8)
for i, (name, letter, role, desc) in enumerate(AGENTS):
    x = start_x + i * Inches(0.72)
    add_avatar_circle(slide, x, y, avatar_size, letter, AGENT_BG[name], AGENT_COLORS[name])

add_text(slide, Inches(0), Inches(5.0), W, Inches(0.4), 'Pre-Seed Pitch · 2026', font_size=13, color=TEXT3, alignment=PP_ALIGN.CENTER)


# ═══════════════════════════════════════════════
# SLIDE 2: PROBLEM
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.5), 'THE PROBLEM')
add_title(slide, Inches(0.8), Inches(0.9), "Companies can't afford great HR")
add_subtitle(slide, Inches(0.8), Inches(1.6), 'Most companies either have no HR at all, or an overwhelmed team buried in admin work.')

# SMB card
card1 = add_rounded_rect(slide, Inches(0.8), Inches(2.3), Inches(5.5), Inches(2.4))
add_text(slide, Inches(1.1), Inches(2.4), Inches(5), Inches(0.4), 'Small & Mid-Size (10-500 employees)', font_size=15, bold=True, color=TEXT)
bullets1 = [
    'No HR department — founders do it on the side',
    '5-10 fragmented SaaS tools with no integration',
    'Compliance risk, poor hiring, employee dissatisfaction',
    "Can't justify a 562K-1.1M SAR CHRO hire"
]
for j, b in enumerate(bullets1):
    add_text(slide, Inches(1.3), Inches(2.9 + j * 0.38), Inches(4.8), Inches(0.35), f'• {b}', font_size=13, color=TEXT2)

# Growing card
card2 = add_rounded_rect(slide, Inches(0.8), Inches(4.9), Inches(5.5), Inches(1.8))
add_text(slide, Inches(1.1), Inches(5.0), Inches(5), Inches(0.4), 'Growing Companies (500+ employees)', font_size=15, bold=True, color=TEXT)
bullets2 = [
    '60-70% of HR time goes to transactional tasks',
    'Inconsistent quality across the team',
    'Reactive, not proactive — always firefighting'
]
for j, b in enumerate(bullets2):
    add_text(slide, Inches(1.3), Inches(5.5 + j * 0.38), Inches(4.8), Inches(0.35), f'• {b}', font_size=13, color=TEXT2)

# Big stat
stat_box = add_rounded_rect(slide, Inches(7.0), Inches(2.3), Inches(5.5), Inches(4.4))
add_text(slide, Inches(7.0), Inches(3.4), Inches(5.5), Inches(0.9), '4.5M SAR', font_size=48, bold=True, color=RED, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(7.0), Inches(4.3), Inches(5.5), Inches(0.5), 'Average annual cost of a full HR department', font_size=15, color=TEXT2, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(7.0), Inches(4.9), Inches(5.5), Inches(0.4), "That's before tools, legal, and compliance costs", font_size=12, color=TEXT3, alignment=PP_ALIGN.CENTER)


# ═══════════════════════════════════════════════
# SLIDE 3: SOLUTION
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.4), 'THE SOLUTION')
add_title(slide, Inches(0.8), Inches(0.8), 'A complete AI HR department')
add_subtitle(slide, Inches(0.8), Inches(1.4), '18 specialized virtual employees across 5 divisions. Always on. Always compliant. 90% less than traditional HR.')

card_w = Inches(3.7)
card_h = Inches(2.0)
gap = Inches(0.25)
start_x = Inches(0.8)
start_y = Inches(2.2)

for i, (name, letter, role, desc) in enumerate(AGENTS):
    col = i % 3
    row = i // 3
    x = start_x + col * (card_w + gap)
    y = start_y + row * (card_h + gap)

    card = add_rounded_rect(slide, x, y, card_w, card_h)

    # Avatar
    av_size = Inches(0.45)
    add_avatar_circle(slide, x + Inches(0.2), y + Inches(0.2), av_size, letter, AGENT_BG[name], AGENT_COLORS[name])

    # Name and role
    add_text(slide, x + Inches(0.8), y + Inches(0.18), Inches(2.5), Inches(0.3), name, font_size=14, bold=True, color=TEXT)
    add_text(slide, x + Inches(0.8), y + Inches(0.45), Inches(2.5), Inches(0.25), role, font_size=11, color=TEXT3)

    # Description
    add_text(slide, x + Inches(0.2), y + Inches(0.85), card_w - Inches(0.4), Inches(1.0), desc, font_size=12, color=TEXT2)


# ═══════════════════════════════════════════════
# SLIDE 4: PRODUCT DEMO
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.4), 'PRODUCT')
add_title(slide, Inches(0.8), Inches(0.8), 'See Krew in action')
add_subtitle(slide, Inches(0.8), Inches(1.4), 'Employees interact with named virtual colleagues through channels they already use.')

# Mockup frame
frame = add_rounded_rect(slide, Inches(1.5), Inches(2.1), Inches(10.3), Inches(4.6))
# Title bar
bar = add_rounded_rect(slide, Inches(1.5), Inches(2.1), Inches(10.3), Inches(0.5), fill_color=RGBColor(0xF5, 0xF5, 0xF4))
add_text(slide, Inches(1.5), Inches(2.15), Inches(10.3), Inches(0.4), 'Krew — Employee Portal', font_size=11, color=TEXT3, alignment=PP_ALIGN.CENTER)

# Sidebar
sidebar = add_rounded_rect(slide, Inches(1.5), Inches(2.6), Inches(2.2), Inches(4.1), fill_color=RGBColor(0xF5, 0xF5, 0xF4))
add_text(slide, Inches(1.7), Inches(2.7), Inches(1.8), Inches(0.3), 'YOUR KREW', font_size=9, bold=True, color=TEXT3)

for i, (name, letter, role, desc) in enumerate(AGENTS):
    sy = Inches(3.05) + i * Inches(0.52)
    av_s = Inches(0.32)
    add_avatar_circle(slide, Inches(1.7), sy, av_s, letter, AGENT_BG[name], AGENT_COLORS[name])
    c = ACCENT if i == 0 else TEXT2
    add_text(slide, Inches(2.1), sy + Inches(0.02), Inches(1.3), Inches(0.3), name, font_size=12, bold=(i==0), color=c)

# Chat messages
chat_x = Inches(4.0)

# User msg 1
um1 = add_rounded_rect(slide, Inches(7.5), Inches(2.8), Inches(4.0), Inches(0.55), fill_color=ACCENT, border_color=ACCENT)
add_text(slide, Inches(7.7), Inches(2.85), Inches(3.6), Inches(0.4), 'How many vacation days do I have left?', font_size=12, color=WHITE)

# Bot msg 1
bm1 = add_rounded_rect(slide, chat_x, Inches(3.5), Inches(6.0), Inches(1.3), fill_color=RGBColor(0xF5, 0xF5, 0xF4), border_color=RGBColor(0xF5, 0xF5, 0xF4))
add_text(slide, chat_x + Inches(0.2), Inches(3.55), Inches(2), Inches(0.25), 'Deema · Employee Services', font_size=9, bold=True, color=ACCENT)
add_text(slide, chat_x + Inches(0.2), Inches(3.8), Inches(5.5), Inches(0.9),
    'You have 14 days of annual leave remaining out of 21 days for 2026.\nYou\'ve used 5 days in January and 2 days in February.\n\nWould you like to submit a leave request?',
    font_size=11, color=TEXT)

# User msg 2
um2 = add_rounded_rect(slide, Inches(7.5), Inches(5.0), Inches(4.0), Inches(0.5), fill_color=ACCENT, border_color=ACCENT)
add_text(slide, Inches(7.7), Inches(5.05), Inches(3.6), Inches(0.4), "Yes, I'd like to take March 15-19 off", font_size=12, color=WHITE)

# Bot msg 2
bm2 = add_rounded_rect(slide, chat_x, Inches(5.65), Inches(6.0), Inches(0.95), fill_color=RGBColor(0xF5, 0xF5, 0xF4), border_color=RGBColor(0xF5, 0xF5, 0xF4))
add_text(slide, chat_x + Inches(0.2), Inches(5.7), Inches(2), Inches(0.25), 'Leave Request Submitted', font_size=9, bold=True, color=GREEN)
add_text(slide, chat_x + Inches(0.2), Inches(5.95), Inches(5.5), Inches(0.6),
    'Done! I\'ve submitted your leave request for Mar 15-19 (5 days).\nYour manager has been notified. You\'ll have 9 days remaining.',
    font_size=11, color=TEXT)


# ═══════════════════════════════════════════════
# SLIDE 5: HOW IT WORKS
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.5), 'HOW IT WORKS')
add_title(slide, Inches(0.8), Inches(0.9), 'Live in hours. Not months.')
add_subtitle(slide, Inches(0.8), Inches(1.5), 'Five steps to deploy your AI HR department.')

steps = [
    ('1', 'Sign Up', 'Choose your plan and connect your channels — WhatsApp, Slack, Teams, or email.'),
    ('2', 'Upload Policies', 'Upload your HR policies and employee handbook. Or let our AI generate them.'),
    ('3', 'Krew Deploys', '18 virtual employees go live instantly. They know your policies from day one.'),
    ('4', 'Employees Interact', 'Your team asks questions, requests leave, onboards — through channels they already use.'),
    ('5', 'You Oversee', 'The CHRO dashboard gives you real-time visibility into your entire HR operation.'),
]

step_w = Inches(2.2)
start_x = Inches(0.6)
step_y = Inches(2.5)

for i, (num, title, desc) in enumerate(steps):
    x = start_x + i * Inches(2.5)

    # Number circle
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.7), step_y, Inches(0.6), Inches(0.6))
    circle.fill.solid()
    circle.fill.fore_color.rgb = ACCENT
    circle.line.fill.background()
    tf = circle.text_frame
    p = tf.paragraphs[0]
    p.text = num
    p.font.size = Pt(20)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.font.name = 'Calibri'
    p.alignment = PP_ALIGN.CENTER

    # Connector line
    if i < len(steps) - 1:
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x + Inches(1.35), step_y + Inches(0.27), Inches(1.5), Inches(0.04))
        line.fill.solid()
        line.fill.fore_color.rgb = BORDER
        line.line.fill.background()

    # Title
    add_text(slide, x, step_y + Inches(0.8), step_w, Inches(0.35), title, font_size=15, bold=True, color=TEXT, alignment=PP_ALIGN.CENTER)

    # Description
    add_text(slide, x, step_y + Inches(1.2), step_w, Inches(1.2), desc, font_size=12, color=TEXT2, alignment=PP_ALIGN.CENTER)


# ═══════════════════════════════════════════════
# SLIDE 6: MARKET OPPORTUNITY
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.4), 'MARKET OPPORTUNITY')
add_title(slide, Inches(0.8), Inches(0.8), 'A massive and growing market')
add_subtitle(slide, Inches(0.8), Inches(1.4), 'We sit at the intersection of HR software, HR outsourcing, and the AI agent economy.')

# TAM / SAM / SOM circles
markets = [
    ('TAM', '2T+ SAR', 'Global HR software +\noutsourcing + PEO', Inches(2.8), RGBColor(0xED, 0xED, 0xFB)),
    ('SAM', '270B SAR', 'English + GCC,\n10-5K employees', Inches(2.2), RGBColor(0xE4, 0xE3, 0xFA)),
    ('SOM', '84M SAR', '500 companies\nby Year 3', Inches(1.8), RGBColor(0xDB, 0xD9, 0xF9)),
]

circle_x_positions = [Inches(1.5), Inches(5.0), Inches(8.5)]
circle_y = Inches(2.2)

for i, (label, value, desc, size, bg) in enumerate(markets):
    cx = circle_x_positions[i]
    cy = circle_y
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, cx, cy, size, size)
    circle.fill.solid()
    circle.fill.fore_color.rgb = bg
    circle.line.color.rgb = ACCENT
    circle.line.width = Pt(2)

    add_text(slide, cx, cy + size * 0.2, size, Inches(0.25), label, font_size=11, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
    add_text(slide, cx, cy + size * 0.35, size, Inches(0.4), value, font_size=24, bold=True, color=TEXT, alignment=PP_ALIGN.CENTER)
    add_text(slide, cx + Inches(0.2), cy + size * 0.6, size - Inches(0.4), Inches(0.6), desc, font_size=10, color=TEXT2, alignment=PP_ALIGN.CENTER)

add_text(slide, Inches(0), Inches(5.2), W, Inches(0.4), 'AI in HR market growing at 30-35% CAGR — the fastest-growing segment in HR tech.', font_size=14, color=TEXT2, alignment=PP_ALIGN.CENTER)

# Revenue projections row
rev_data = [('1.8M SAR', 'Year 1 Revenue'), ('12M SAR', 'Year 2 Revenue'), ('84M SAR', 'Year 3 Revenue')]
for i, (val, lbl) in enumerate(rev_data):
    bx = Inches(1.5) + i * Inches(3.8)
    add_rounded_rect(slide, bx, Inches(5.8), Inches(3.3), Inches(1.2))
    add_text(slide, bx, Inches(5.95), Inches(3.3), Inches(0.5), val, font_size=24, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
    add_text(slide, bx, Inches(6.45), Inches(3.3), Inches(0.3), lbl, font_size=12, color=TEXT2, alignment=PP_ALIGN.CENTER)


# ═══════════════════════════════════════════════
# SLIDE 7: BUSINESS MODEL
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.4), 'BUSINESS MODEL')
add_title(slide, Inches(0.8), Inches(0.8), 'Per-employee-per-month. Simple, scalable.')
add_subtitle(slide, Inches(0.8), Inches(1.4), 'All 18 virtual employees and all 5 divisions included in every plan.')

pricing = [
    ('Starter', '9,375', 'SAR / month', 'Up to 50 employees\n2 channels · Policy RAG · Email support', False),
    ('Growth', '22,500', 'SAR / month', 'Up to 250 employees\nAll channels · Agent Factory · CHRO dashboard', True),
    ('Enterprise', 'Custom', '', '250+ employees\nCustom training · SLA · Dedicated success manager', False),
]

for i, (tier, price, unit, features, featured) in enumerate(pricing):
    px = Inches(0.8) + i * Inches(4.1)
    bc = ACCENT if featured else BORDER
    card = add_rounded_rect(slide, px, Inches(2.2), Inches(3.7), Inches(3.0), border_color=bc)
    if featured:
        card.line.width = Pt(2)
        badge = add_rounded_rect(slide, px + Inches(0.9), Inches(2.05), Inches(1.9), Inches(0.35), fill_color=ACCENT, border_color=ACCENT)
        add_text(slide, px + Inches(0.9), Inches(2.07), Inches(1.9), Inches(0.3), 'MOST POPULAR', font_size=9, bold=True, color=WHITE, alignment=PP_ALIGN.CENTER)

    add_text(slide, px, Inches(2.5), Inches(3.7), Inches(0.35), tier, font_size=14, bold=True, color=TEXT, alignment=PP_ALIGN.CENTER)
    add_text(slide, px, Inches(2.9), Inches(3.7), Inches(0.6), price, font_size=32, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
    if unit:
        add_text(slide, px, Inches(3.4), Inches(3.7), Inches(0.3), unit, font_size=13, color=TEXT3, alignment=PP_ALIGN.CENTER)
    add_text(slide, px + Inches(0.3), Inches(3.8), Inches(3.1), Inches(1.2), features, font_size=12, color=TEXT3, alignment=PP_ALIGN.CENTER)

# Bottom metrics
metrics = [('85%+', 'Gross Margins'), ('28x', 'LTV : CAC'), ('115%', 'Net Revenue Retention')]
for i, (val, lbl) in enumerate(metrics):
    mx = Inches(0.8) + i * Inches(4.1)
    add_rounded_rect(slide, mx, Inches(5.5), Inches(3.7), Inches(1.2))
    add_text(slide, mx, Inches(5.65), Inches(3.7), Inches(0.5), val, font_size=24, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
    add_text(slide, mx, Inches(6.15), Inches(3.7), Inches(0.3), lbl, font_size=12, color=TEXT2, alignment=PP_ALIGN.CENTER)


# ═══════════════════════════════════════════════
# SLIDE 8: TRACTION
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.5), 'TRACTION')
add_title(slide, Inches(0.8), Inches(0.9), 'Early signals of demand')
add_subtitle(slide, Inches(0.8), Inches(1.5), 'Pre-revenue. Building in public. Saudi market-first launch.')

traction = [
    ('Live', 'Working Prototype', 'Functional product demo with all 5 divisions, chat interface, CHRO dashboard, and Agent Factory.', GREEN, False),
    ('94%', 'Auto-Resolution Rate', 'In prototype testing — employee queries handled without human escalation.', ACCENT, False),
    ('[XX]', 'Waitlist Signups', 'Landing page live at krew.sa — collecting interest from Saudi companies.', TEXT3, True),
    ('[XX]', 'LOIs / Pilot Commitments', 'Letters of intent from target companies for beta access.', TEXT3, True),
]

for i, (val, label, desc, color, placeholder) in enumerate(traction):
    col = i % 2
    row = i // 2
    tx = Inches(0.8) + col * Inches(6.0)
    ty = Inches(2.3) + row * Inches(2.4)
    bc = TEXT3 if placeholder else BORDER
    card = add_rounded_rect(slide, tx, ty, Inches(5.5), Inches(2.0), border_color=bc)
    if placeholder:
        card.line.dash_style = 2  # dash
    add_text(slide, tx + Inches(0.3), ty + Inches(0.2), Inches(4.9), Inches(0.5), val, font_size=24, bold=True, color=color)
    add_text(slide, tx + Inches(0.3), ty + Inches(0.7), Inches(4.9), Inches(0.35), label, font_size=14, bold=False, color=TEXT2)
    add_text(slide, tx + Inches(0.3), ty + Inches(1.15), Inches(4.9), Inches(0.6), desc, font_size=12, color=TEXT3)


# ═══════════════════════════════════════════════
# SLIDE 9: COMPETITION
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.3), 'COMPETITIVE LANDSCAPE')
add_title(slide, Inches(0.8), Inches(0.65), 'No one is building a full-stack AI HR department')
add_subtitle(slide, Inches(0.8), Inches(1.25), 'Everyone is either adding AI to legacy platforms, or solving one HR problem.')

# 2x2 Grid
gx, gy = Inches(1.8), Inches(2.0)
gw, gh = Inches(9.5), Inches(4.5)
mid_x = gx + gw / 2
mid_y = gy + gh / 2

# Axes
x_axis = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, gx, gy + gh, gw, Pt(2))
x_axis.fill.solid(); x_axis.fill.fore_color.rgb = BORDER; x_axis.line.fill.background()
y_axis = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, gx, gy, Pt(2), gh)
y_axis.fill.solid(); y_axis.fill.fore_color.rgb = BORDER; y_axis.line.fill.background()

# Dashed mid lines
mid_h = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, gx, mid_y, gw, Pt(1))
mid_h.fill.solid(); mid_h.fill.fore_color.rgb = BORDER; mid_h.line.fill.background()
mid_v = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mid_x, gy, Pt(1), gh)
mid_v.fill.solid(); mid_v.fill.fore_color.rgb = BORDER; mid_v.line.fill.background()

# Axis labels
add_text(slide, gx, gy + gh + Inches(0.1), gw, Inches(0.3), 'HR Coverage →', font_size=11, bold=True, color=TEXT2, alignment=PP_ALIGN.CENTER)
add_text(slide, gx + Inches(0.15), gy + gh - Inches(0.15), Inches(1.5), Inches(0.25), 'Single Function', font_size=9, color=TEXT3)
add_text(slide, gx + gw - Inches(1.7), gy + gh - Inches(0.15), Inches(1.5), Inches(0.25), 'Full Department', font_size=9, color=TEXT3)
add_text(slide, gx - Inches(1.4), gy + gh - Inches(0.5), Inches(1.3), Inches(0.25), 'Human-\nDependent', font_size=9, color=TEXT3)
add_text(slide, gx - Inches(1.3), gy + Inches(0.1), Inches(1.2), Inches(0.25), 'AI-Native', font_size=9, color=TEXT3)

# Quadrant labels
add_text(slide, gx + Inches(0.5), gy + Inches(0.15), Inches(3.5), Inches(0.25), 'AI POINT SOLUTIONS', font_size=9, bold=True, color=TEXT3, alignment=PP_ALIGN.CENTER)
add_text(slide, mid_x + Inches(0.5), gy + Inches(0.15), Inches(3.5), Inches(0.25), 'AI HR DEPARTMENT', font_size=9, bold=True, color=TEXT3, alignment=PP_ALIGN.CENTER)
add_text(slide, gx + Inches(0.5), mid_y + Inches(0.8), Inches(3.5), Inches(0.25), 'LEGACY HRO', font_size=9, bold=True, color=TEXT3, alignment=PP_ALIGN.CENTER)
add_text(slide, mid_x + Inches(0.5), mid_y + Inches(0.8), Inches(3.5), Inches(0.25), 'TRADITIONAL HCM', font_size=9, bold=True, color=TEXT3, alignment=PP_ALIGN.CENTER)

# Competitor dots
competitors = [
    # (name, x_ratio, y_ratio) - x: 0=left, 1=right; y: 0=top, 1=bottom
    ('TriNet', 0.15, 0.8), ('ADP', 0.25, 0.85), ('Deel', 0.32, 0.72),
    ('Workday', 0.7, 0.72), ('SAP', 0.78, 0.8), ('BambooHR', 0.6, 0.68),
    ('Leena AI', 0.13, 0.2), ('Paradox', 0.25, 0.12), ('Eightfold', 0.33, 0.22), ('Beamery', 0.2, 0.3),
]

for name, xr, yr in competitors:
    cx = gx + int(gw * xr)
    cy = gy + int(gh * yr)
    dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, cx, cy, Inches(0.15), Inches(0.15))
    dot.fill.solid(); dot.fill.fore_color.rgb = TEXT3; dot.line.fill.background()
    add_text(slide, cx - Inches(0.4), cy + Inches(0.18), Inches(1.0), Inches(0.25), name, font_size=9, color=TEXT2, alignment=PP_ALIGN.CENTER)

# KREW - big dot
krew_x = gx + int(gw * 0.78)
krew_y = gy + int(gh * 0.1)
krew_ring = slide.shapes.add_shape(MSO_SHAPE.OVAL, krew_x - Inches(0.2), krew_y - Inches(0.2), Inches(0.7), Inches(0.7))
krew_ring.fill.solid(); krew_ring.fill.fore_color.rgb = RGBColor(0xED, 0xED, 0xFB); krew_ring.line.color.rgb = ACCENT; krew_ring.line.width = Pt(2)
krew_dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, krew_x, krew_y, Inches(0.3), Inches(0.3))
krew_dot.fill.solid(); krew_dot.fill.fore_color.rgb = ACCENT; krew_dot.line.fill.background()
add_text(slide, krew_x - Inches(0.3), krew_y - Inches(0.35), Inches(0.9), Inches(0.3), 'Krew', font_size=13, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)

add_text(slide, Inches(1.5), Inches(6.7), Inches(10), Inches(0.4),
    'Krew is the only company building a complete AI-native HR department — all 5 divisions, 18 virtual employees, one subscription.',
    font_size=14, color=TEXT2, alignment=PP_ALIGN.CENTER)


# ═══════════════════════════════════════════════
# SLIDE 10: TEAM
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.4), 'THE TEAM')
add_title(slide, Inches(0.8), Inches(0.8), 'Why we win')
add_subtitle(slide, Inches(0.8), Inches(1.4), 'Brother & sister. HR domain expertise meets AI technical capability.')

# Ahmad card
card_w = Inches(5.5)
add_rounded_rect(slide, Inches(0.8), Inches(2.2), card_w, Inches(2.6))
add_avatar_circle(slide, Inches(3.0), Inches(2.4), Inches(0.8), 'A', RGBColor(0xED, 0xED, 0xFB), ACCENT)
add_text(slide, Inches(0.8), Inches(3.3), card_w, Inches(0.35), 'Ahmad Al Ghamdi', font_size=17, bold=True, color=TEXT, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(0.8), Inches(3.6), card_w, Inches(0.3), 'Co-Founder & CEO', font_size=13, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(1.1), Inches(3.95), Inches(5.0), Inches(0.7),
    'CHRO at stc (Saudi Telecom). One of the founding leaders of HR in Saudi Arabia. Deep expertise in Saudi labor market, workforce regulations (Nitaqat, GOSI, MOL), and organizational transformation. INSEAD alumnus.',
    font_size=12, color=TEXT2, alignment=PP_ALIGN.CENTER)

# Najwa card
add_rounded_rect(slide, Inches(7.0), Inches(2.2), card_w, Inches(2.6))
add_avatar_circle(slide, Inches(9.2), Inches(2.4), Inches(0.8), 'N', RGBColor(0xFC, 0xE7, 0xF3), PINK)
add_text(slide, Inches(7.0), Inches(3.3), card_w, Inches(0.35), 'Najwa Al Ghamdi', font_size=17, bold=True, color=TEXT, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(7.0), Inches(3.6), card_w, Inches(0.3), 'Co-Founder & CTO', font_size=13, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(7.3), Inches(3.95), Inches(5.0), Inches(0.7),
    'General Manager — AI & Analytics. One of the very few Saudis in Corporate AI. Technical expertise in AI/LLM systems, agent frameworks, RAG architectures, and full-stack development.',
    font_size=12, color=TEXT2, alignment=PP_ALIGN.CENTER)

# Why we win bullets
bullets = [
    ('Founder-market fit', 'Ahmad is a founding leader of HR in Saudi as CHRO of stc; Najwa is one of the very few Saudis leading Corporate AI'),
    ('First-mover advantage', 'No competitor is building a complete AI HR department. We own the category.'),
    ('Saudi market-first', 'Launching where we know the regulations, the culture, and the customers. Then expanding to GCC and globally.'),
    ('AI-native from day one', 'No legacy code, no technical debt. Built for the agent economy.'),
]

for i, (title, desc) in enumerate(bullets):
    bx = Inches(0.8) + (i % 2) * Inches(6.2)
    by = Inches(5.15) + (i // 2) * Inches(0.85)
    add_text(slide, bx, by, Inches(5.8), Inches(0.3), f'→  {title}', font_size=14, bold=True, color=ACCENT)
    add_text(slide, bx + Inches(0.35), by + Inches(0.3), Inches(5.5), Inches(0.5), desc, font_size=12, color=TEXT2)


# ═══════════════════════════════════════════════
# SLIDE 11: FINANCIALS & ASK
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_section_label(slide, Inches(0.8), Inches(0.4), 'FINANCIALS & THE ASK')
add_title(slide, Inches(0.8), Inches(0.8), 'Raising 2.8M SAR Pre-Seed')
add_subtitle(slide, Inches(0.8), Inches(1.4), 'Clear path from pre-seed to scale.')

# Bar chart
bars = [
    ('Year 1', '2.4M', 0.08),
    ('Year 2', '12.8M', 0.18),
    ('Year 3', '37.5M', 0.35),
    ('Year 4', '112.5M', 0.60),
    ('Year 5', '300M', 1.0),
]

chart_left = Inches(0.8)
chart_bottom = Inches(6.2)
chart_h = Inches(3.5)
bar_w = Inches(0.9)

# Chart baseline
baseline = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, chart_left, chart_bottom, Inches(6.0), Pt(2))
baseline.fill.solid(); baseline.fill.fore_color.rgb = BORDER; baseline.line.fill.background()

add_text(slide, chart_left, Inches(2.0), Inches(5), Inches(0.3), 'Revenue Projections — ARR (SAR)', font_size=12, bold=True, color=TEXT2)

opacities = [0.4, 0.55, 0.7, 0.85, 1.0]
accent_shades = [
    RGBColor(0x9B, 0x95, 0xF0),
    RGBColor(0x84, 0x7C, 0xED),
    RGBColor(0x6D, 0x64, 0xEA),
    RGBColor(0x5E, 0x55, 0xE7),
    ACCENT,
]

for i, (year, value, ratio) in enumerate(bars):
    bx = chart_left + Inches(0.2) + i * Inches(1.15)
    bh = int(chart_h * ratio)
    by = chart_bottom - bh

    bar = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, bx, by, bar_w, bh)
    bar.fill.solid()
    bar.fill.fore_color.rgb = accent_shades[i]
    bar.line.fill.background()
    bar.adjustments[0] = 0.08

    add_text(slide, bx - Inches(0.15), by - Inches(0.3), bar_w + Inches(0.3), Inches(0.3), value, font_size=11, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
    add_text(slide, bx - Inches(0.15), chart_bottom + Inches(0.1), bar_w + Inches(0.3), Inches(0.3), year, font_size=11, bold=True, color=TEXT2, alignment=PP_ALIGN.CENTER)

# Right side - Ask box
ask_x = Inches(7.2)
ask_box = add_rounded_rect(slide, ask_x, Inches(2.0), Inches(5.3), Inches(1.3), fill_color=RGBColor(0xED, 0xED, 0xFB), border_color=RGBColor(0xD6, 0xD3, 0xF8))
add_text(slide, ask_x, Inches(2.15), Inches(5.3), Inches(0.6), '2.8M SAR', font_size=32, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
add_text(slide, ask_x, Inches(2.7), Inches(5.3), Inches(0.4), 'Pre-Seed · SAFE at 19-30M SAR valuation cap', font_size=13, color=TEXT2, alignment=PP_ALIGN.CENTER)

# Use of funds
add_text(slide, ask_x, Inches(3.5), Inches(5), Inches(0.3), 'Use of Funds', font_size=12, bold=True, color=TEXT2)

funds = [
    ('Engineering', 0.40, ACCENT),
    ('LLM/Infra', 0.13, ACCENT2),
    ('Legal', 0.07, RGBColor(0x81, 0x8C, 0xF8)),
    ('Marketing', 0.13, BLUE),
    ('Salaries', 0.20, GREEN),
    ('Buffer', 0.07, TEXT3),
]

fund_bar_x = ask_x
fund_bar_y = Inches(3.85)
fund_bar_w = Inches(5.3)
fund_bar_h = Inches(0.35)

cx = fund_bar_x
for label, pct, color in funds:
    w = int(fund_bar_w * pct)
    seg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, fund_bar_y, w, fund_bar_h)
    seg.fill.solid(); seg.fill.fore_color.rgb = color; seg.line.fill.background()
    if pct >= 0.13:
        add_text(slide, cx, fund_bar_y + Inches(0.02), w, fund_bar_h - Inches(0.04), f'{int(pct*100)}%', font_size=9, bold=True, color=WHITE, alignment=PP_ALIGN.CENTER)
    cx += w

# Legend
for i, (label, pct, color) in enumerate(funds):
    col = i % 3
    row = i // 3
    lx = ask_x + col * Inches(1.8)
    ly = Inches(4.35) + row * Inches(0.3)
    dot = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, lx, ly + Inches(0.05), Inches(0.12), Inches(0.12))
    dot.fill.solid(); dot.fill.fore_color.rgb = color; dot.line.fill.background()
    add_text(slide, lx + Inches(0.18), ly, Inches(1.5), Inches(0.25), f'{label} {int(pct*100)}%', font_size=10, color=TEXT2)

# Milestones
add_text(slide, ask_x, Inches(5.1), Inches(5), Inches(0.3), '18-Month Milestones', font_size=12, bold=True, color=TEXT2)
milestones = [
    'Launch MVP — Employee Services Agent live',
    '20+ paying customers in Saudi Arabia',
    '1.9M SAR ARR milestone',
    'Raise Seed round (7.5-15M SAR)',
]
for i, m in enumerate(milestones):
    add_text(slide, ask_x + Inches(0.3), Inches(5.45) + i * Inches(0.35), Inches(4.8), Inches(0.3), f'○  {m}', font_size=12, color=TEXT2)


# ═══════════════════════════════════════════════
# SLIDE 12: CLOSING
# ═══════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)

add_text(slide, Inches(0), Inches(1.5), W, Inches(0.8), 'Every company will have an AI HR department.', font_size=40, bold=True, color=TEXT, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(0), Inches(2.4), W, Inches(0.8), "We're building it.", font_size=40, bold=True, color=ACCENT, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(0), Inches(3.5), W, Inches(0.4), 'Krew — Your AI HR Department', font_size=16, bold=True, color=TEXT2, alignment=PP_ALIGN.CENTER)

# Agent avatars
avatar_size = Inches(0.48)
start_x = Inches(4.85)
y = Inches(4.2)
for i, (name, letter, role, desc) in enumerate(AGENTS):
    x = start_x + i * Inches(0.65)
    add_avatar_circle(slide, x, y, avatar_size, letter, AGENT_BG[name], AGENT_COLORS[name])

# CTA button
btn = add_rounded_rect(slide, Inches(5.5), Inches(5.2), Inches(2.3), Inches(0.6), fill_color=ACCENT, border_color=ACCENT)
add_text(slide, Inches(5.5), Inches(5.25), Inches(2.3), Inches(0.5), "Let's talk", font_size=16, bold=True, color=WHITE, alignment=PP_ALIGN.CENTER)

add_text(slide, Inches(0), Inches(6.1), W, Inches(0.3), 'Ahmad Al Ghamdi & Najwa Al Ghamdi', font_size=14, color=TEXT3, alignment=PP_ALIGN.CENTER)
add_text(slide, Inches(0), Inches(6.4), W, Inches(0.3), 'krew.sa', font_size=14, color=TEXT3, alignment=PP_ALIGN.CENTER)


# ─── SAVE ───
output_path = os.path.join(os.path.dirname(__file__), 'pitch-deck.pptx')
prs.save(output_path)
print(f'Saved to: {output_path}')
