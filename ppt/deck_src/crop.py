from PIL import Image
import os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
def crop(src, box, out):
    im = Image.open(os.path.join(D, src)).crop(box)
    im.save(os.path.join(D, out)); print(out, im.size)
crop("board_full.png", (0, 52, 1920, 1080), "board_hero.png")
crop("leads.png", (255, 190, 1582, 492), "leads_card.png")
crop("casefile.png", (1242, 176, 1584, 868), "casefile_panel.png")
crop("audit.png", (255, 125, 1582, 700), "audit_panel.png")
