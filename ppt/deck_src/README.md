# Regenerate the SIH idea deck

    cd ppt/deck_src && npm install pptxgenjs && node make_deck.js ../PRAHARI_SIH2026_Idea.pptx

Screenshots in shots/ were captured from the running board with headless Chrome:

    chrome --headless=new --window-size=1920,1080 --virtual-time-budget=14000 --screenshot=board_full.png "http://localhost:8000/?full=1"

Deep links the board accepts: ?view=leads|audit|ingestion|timeline · ?entity=Name&tab=casefile · ?full=1
