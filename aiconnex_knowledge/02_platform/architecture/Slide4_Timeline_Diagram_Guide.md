# Slide 4: Timeline & Market Gap Diagram Guide
## AIConnex Executive Pitch Deck — Visual Asset & Code Reference

---

> **Purpose**: This guide provides both the raw copy-pasteable Mermaid diagram code and the high-resolution rendered graphic for **Slide 4 ("Why Most AI Projects Stall Before They Even Start")**.

---

## 🖼️ 1. Rendered Visual Diagram

![Slide 4 Rendered Flowchart Diagram](C:\Users\aksha\.gemini\antigravity\brain\aca1036f-deab-4f13-a6cc-12be286d4791\slide4_flowchart_rendered_1785949056183.jpg)

---

## 💻 2. Raw Mermaid Code (Copy & Paste Ready)

Use this raw text code in diagram editors such as **Eraser.io**, **Napkin AI**, **Mermaid Live Editor**, **Notion**, or **Canva App**:

```mermaid
flowchart TD
    subgraph TOP["🔴 TRADITIONAL INDUSTRIAL JOURNEY (16 WEEKS TOTAL)"]
        direction LR
        A["1. Collect Data<br/>(Wks 1–3)"] --> B["2. Clean Data<br/>(Wks 4–7)"]
        B --> C["3. Feature Eng.<br/>(Wks 8–11)"] --> D["4. Select Features<br/>(Wks 12–13)"]
        D --> E["5. Train & Deploy<br/>(Wks 14–16)"]
    end

    subgraph BOTTOM["🔵 MARKET TOOLING vs THE INDUSTRIAL GAP"]
        direction LR
        GAP["⚠️ 100% MANUAL GAP (Weeks 1–13)<br/>Raw ZIPs, SCADA Workbooks & Sensor Logs<br/>(Unsolved by Existing Market Tools)"] 
        AUTO["⚡ AUTOMATED BY AUTOML (Weeks 14–16)<br/>Model Training & Feature Stores<br/>(Assumes Clean Tabular Data)"]
        GAP --> AUTO
    end

    classDef red fill:#fecdd3,stroke:#e11d48,color:#881337,font-weight:bold;
    classDef green fill:#dcfce7,stroke:#16a34a,color:#14532d,font-weight:bold;
    classDef blue fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e;
    
    class GAP red;
    class AUTO green;
    class E green;
    class A,B,C,D blue;
```

---

## 📝 3. Slide 4 Content Summary

* **Header**: Why Most AI Projects Stall Before They Even Start
* **Subtitle**: Teams spend most of their time preparing data — and by the time the model is ready, the budget and patience are gone.
* **Key Message**: Existing market tools (Feature Stores & AutoML) automated the second half (*after data is clean*). AIConnex solves the hardest first half (*getting messy raw industrial data clean in the first place*).
