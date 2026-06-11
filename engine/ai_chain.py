# engine/ai_chain.py
"""The AI market's end-to-end supply chain, as an investable taxonomy.

Ten layers, ordered roughly by where value flows: designing chips ->
making them -> connecting them -> housing and powering them -> renting
them -> building models and products on top. Each layer carries a plain
-English role, the question that decides whether it re-rates next
("what to watch"), and the liquid public names that express it.

This file is DATA ONLY (plus tiny accessors) so the scanner, the tests,
and the dashboard all share one source of truth. Curated June 2026;
revisit quarterly — the bottleneck moves.
"""
from typing import Dict, List

# Each company: symbol (yfinance), note (its role in the layer, shown in the UI).
LAYERS: List[Dict] = [
    {
        "key": "silicon_ip",
        "name": "Silicon IP & EDA",
        "role": ("Where every chip starts: instruction-set licences and the design "
                 "software no chipmaker can ship without. Royalty-like economics, "
                 "agnostic to who wins the chip race."),
        "watch": ("Licence/royalty growth and AI-driven design starts; EDA pricing "
                  "power as chip complexity explodes."),
        "companies": [
            {"symbol": "ARM", "note": "CPU architecture licensed across phones, servers, AI accelerators"},
            {"symbol": "SNPS", "note": "EDA design software + interface IP duopolist"},
            {"symbol": "CDNS", "note": "the other half of the EDA duopoly"},
        ],
    },
    {
        "key": "chip_design",
        "name": "Accelerators & Logic",
        "role": ("The compute itself: GPUs, custom AI ASICs, and the CPUs that "
                 "host them. The layer that re-rated first (2023-24) and still "
                 "sets the tone for the whole chain."),
        "watch": ("Hyperscaler capex guides; custom-silicon (ASIC) share vs GPUs; "
                  "inference vs training mix."),
        "companies": [
            {"symbol": "NVDA", "note": "dominant AI GPU + networking platform"},
            {"symbol": "AMD", "note": "GPU challenger; MI-series accelerators"},
            {"symbol": "AVGO", "note": "custom AI ASICs for hyperscalers + networking silicon"},
            {"symbol": "MRVL", "note": "custom silicon, electro-optics, interconnect"},
            {"symbol": "QCOM", "note": "edge/on-device AI silicon"},
            {"symbol": "INTC", "note": "x86 host CPUs + foundry turnaround optionality"},
        ],
    },
    {
        "key": "memory_storage",
        "name": "Memory & Storage",
        "role": ("HBM feeds the GPUs; DRAM and NAND hold the data. The 2025-26 "
                 "bottleneck: all three HBM makers pre-sold their capacity and the "
                 "commodity cycle broke upward — the layer of the Micron trade."),
        "watch": ("HBM pricing and capacity adds; DRAM/NAND spot prices; data-centre "
                  "share of bit demand (now >50% for the first time)."),
        "companies": [
            {"symbol": "MU", "note": "HBM + DRAM/NAND; the US memory pure-play"},
            {"symbol": "000660.KS", "note": "SK hynix — HBM market leader (KRX, ₩)"},
            {"symbol": "005930.KS", "note": "Samsung Electronics — memory giant (KRX, ₩)"},
            {"symbol": "WDC", "note": "hard drives for AI data lakes"},
            {"symbol": "STX", "note": "high-capacity drives; AI storage demand"},
            {"symbol": "SNDK", "note": "NAND flash pure-play (ex-WDC)"},
        ],
    },
    {
        "key": "foundry",
        "name": "Foundry & Manufacturing",
        "role": ("Whoever designs the chip, one of these makes it. Advanced "
                 "packaging (CoWoS) capacity is as scarce as wafers."),
        "watch": ("TSMC capex + advanced-node/CoWoS capacity; 2026 revenue guided "
                  ">30% on AI demand; US/Japan fab ramps."),
        "companies": [
            {"symbol": "TSM", "note": "the indispensable advanced-node foundry"},
            {"symbol": "GFS", "note": "trailing-edge + specialty foundry"},
            {"symbol": "UMC", "note": "mature-node foundry"},
        ],
    },
    {
        "key": "equipment_materials",
        "name": "Equipment & Materials",
        "role": ("The picks-and-shovels sellers to every fab on earth: lithography, "
                 "deposition, etch, test, and the ultra-pure materials in between."),
        "watch": ("WFE (wafer-fab equipment) spend forecasts; EUV shipments; "
                  "HBM-driven test/packaging equipment orders."),
        "companies": [
            {"symbol": "ASML", "note": "EUV lithography monopoly"},
            {"symbol": "AMAT", "note": "broadest equipment portfolio"},
            {"symbol": "LRCX", "note": "etch/deposition; HBM stacking exposure"},
            {"symbol": "KLAC", "note": "process control/inspection"},
            {"symbol": "TER", "note": "semiconductor test (HBM, ASICs)"},
            {"symbol": "ENTG", "note": "materials, filtration, handling"},
            {"symbol": "MKSI", "note": "subsystems, lasers, optics"},
        ],
    },
    {
        "key": "networking_optics",
        "name": "Networking & Optics",
        "role": ("AI clusters are only as fast as the fabric between GPUs. "
                 "Switching, retimers, and optical interconnects — a named "
                 "candidate for the next bottleneck after memory."),
        "watch": ("800G/1.6T optics ramps; scale-up vs scale-out fabric wins; "
                  "co-packaged optics timelines."),
        "companies": [
            {"symbol": "ANET", "note": "AI data-centre switching"},
            {"symbol": "ALAB", "note": "PCIe/CXL retimers in AI servers"},
            {"symbol": "CRDO", "note": "high-speed SerDes interconnect"},
            {"symbol": "COHR", "note": "optical transceivers + lasers"},
            {"symbol": "LITE", "note": "optical components for AI clusters"},
            {"symbol": "AAOI", "note": "optics; flagged 2026 bottleneck play"},
            {"symbol": "CIEN", "note": "optical transport between data centres"},
        ],
    },
    {
        "key": "servers_cooling",
        "name": "Servers, Power & Cooling",
        "role": ("Racks, integration, liquid cooling, and in-rack power. Every GPU "
                 "ships inside someone's server with someone's cooling loop."),
        "watch": ("Vertiv backlog (+109% y/y) and NVIDIA power-architecture "
                  "partnership; liquid-cooling attach rates; ODM margins."),
        "companies": [
            {"symbol": "VRT", "note": "power + liquid cooling; most direct buildout play"},
            {"symbol": "ETN", "note": "electrical equipment for data centres"},
            {"symbol": "SMCI", "note": "AI server ODM"},
            {"symbol": "DELL", "note": "AI server scale shipper"},
            {"symbol": "HPE", "note": "servers + networking (Juniper)"},
            {"symbol": "CLS", "note": "hyperscaler rack integration"},
            {"symbol": "JBL", "note": "manufacturing services across AI hardware"},
        ],
    },
    {
        "key": "power_energy",
        "name": "Power Generation & Grid",
        "role": ("The hard constraint nobody can print more of: electrons. Turbines, "
                 "grid equipment, nuclear PPAs, and merchant power for hyperscale "
                 "load — the layer that re-rated through 2025-26."),
        "watch": ("GEV electrification orders (one 2026 quarter beat all of 2025); "
                  "data-centre PPAs; ~$1.4T grid electrification need by 2030."),
        "companies": [
            {"symbol": "GEV", "note": "turbines + grid equipment; AI power bellwether"},
            {"symbol": "CEG", "note": "nuclear fleet, hyperscaler PPAs"},
            {"symbol": "VST", "note": "merchant power + nuclear"},
            {"symbol": "TLN", "note": "nuclear-adjacent merchant power"},
            {"symbol": "NRG", "note": "power generation, data-centre deals"},
            {"symbol": "PWR", "note": "builds the grid: transmission EPC"},
        ],
    },
    {
        "key": "datacenter_cloud",
        "name": "Data Centres & Neoclouds",
        "role": ("The landlords and the GPU-rental upstarts. REITs lease the "
                 "buildings; neoclouds rent raw accelerator capacity by the hour."),
        "watch": ("Leasing pipelines and pricing; neocloud contract backlogs vs "
                  "debt loads; capacity sold out years ahead?"),
        "companies": [
            {"symbol": "EQIX", "note": "interconnection-rich data-centre REIT"},
            {"symbol": "DLR", "note": "hyperscale data-centre REIT"},
            {"symbol": "CRWV", "note": "GPU neocloud at scale"},
            {"symbol": "NBIS", "note": "AI infrastructure / neocloud"},
            {"symbol": "IREN", "note": "power-rich sites pivoted to AI compute"},
            {"symbol": "APLD", "note": "AI data-centre developer"},
        ],
    },
    {
        "key": "models_apps",
        "name": "Hyperscalers, Models & Apps",
        "role": ("Where the spending is supposed to pay off: clouds renting "
                 "intelligence, and software charging for it. The Mag-7 capex "
                 "(~$527B in FY26) funds every layer below."),
        "watch": ("AI revenue disclosure vs capex; agent/inference usage curves; "
                  "whether application-layer margins hold."),
        "companies": [
            {"symbol": "MSFT", "note": "Azure + OpenAI distribution"},
            {"symbol": "GOOGL", "note": "Gemini, TPUs, cloud"},
            {"symbol": "AMZN", "note": "AWS + Trainium silicon"},
            {"symbol": "META", "note": "open models, ad-stack AI, giant capex"},
            {"symbol": "ORCL", "note": "OCI AI cloud backlog"},
            {"symbol": "PLTR", "note": "enterprise AI deployment layer"},
            {"symbol": "NOW", "note": "agentic workflows in the enterprise"},
            {"symbol": "APP", "note": "AI-driven ad engine"},
        ],
    },
]

# ETFs that wrap the theme, tagged by what they actually hold.
ETFS: List[Dict] = [
    {"symbol": "SMH", "note": "large-cap semis (NVDA/TSM/AVGO heavy)"},
    {"symbol": "SOXX", "note": "US-listed semiconductor index"},
    {"symbol": "DRAM", "note": "memory pure-play — the Micron-trade wrapper"},
    {"symbol": "AIQ", "note": "broad AI & tech, 80+ holdings"},
    {"symbol": "ARTY", "note": "concentrated AI infrastructure + Asian chipmakers"},
    {"symbol": "BAI", "note": "active AI infrastructure picks"},
    {"symbol": "CHPX", "note": "full compute stack: chips to power"},
    {"symbol": "AIPO", "note": "AI x energy/power intersection"},
    {"symbol": "GRID", "note": "grid & electrification equipment"},
    {"symbol": "XLU", "note": "utilities — defensive AI-power exposure"},
]

# Relative-strength benchmark for the whole chain view.
BENCHMARK = "SMH"

# Search / news theme per layer, feeding the free attention collectors
# (Google Trends + GDELT). One term each — quotas are tight and a single
# well-chosen phrase beats a basket of noisy ones.
THEMES: Dict[str, Dict[str, str]] = {
    "silicon_ip": {"trends": "chip design AI", "news": "semiconductor IP licensing"},
    "chip_design": {"trends": "AI chips", "news": "AI accelerator chips"},
    "memory_storage": {"trends": "HBM memory", "news": "high-bandwidth memory"},
    "foundry": {"trends": "TSMC", "news": "TSMC advanced packaging"},
    "equipment_materials": {"trends": "EUV lithography", "news": "semiconductor equipment orders"},
    "networking_optics": {"trends": "optical transceiver", "news": "AI cluster networking optics"},
    "servers_cooling": {"trends": "liquid cooling data center", "news": "data center liquid cooling"},
    "power_energy": {"trends": "data center power", "news": "data center power shortage"},
    "datacenter_cloud": {"trends": "GPU cloud", "news": "GPU cloud capacity"},
    "models_apps": {"trends": "AI agents", "news": "enterprise AI agents revenue"},
}


def all_company_symbols() -> List[str]:
    """Every company ticker across all layers (deduped, order preserved)."""
    seen = set()
    out: List[str] = []
    for layer in LAYERS:
        for c in layer["companies"]:
            if c["symbol"] not in seen:
                seen.add(c["symbol"])
                out.append(c["symbol"])
    return out


def all_etf_symbols() -> List[str]:
    return [e["symbol"] for e in ETFS]
