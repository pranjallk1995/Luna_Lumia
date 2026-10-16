import streamlit as st

from config import UIConfig


class LunaStyle:
    @staticmethod
    def apply():
        st.html("""
        <style>
        :root{--lv-bg:#111;--lv-surface:rgba(255,255,255,.055);--lv-control:rgba(255,255,255,.07);--lv-hover:rgba(255,255,255,.12);--lv-text:#f5f5f5;--lv-muted:#a3a3a3;--lv-border:rgba(255,255,255,.14);--lv-strong:rgba(255,255,255,.34);--lv-soft:rgba(255,255,255,.09)}
        .stApp{color:var(--lv-text);background:radial-gradient(circle at 82% -10%,rgba(255,255,255,.07),transparent 30rem),var(--lv-bg)}
        .block-container{max-width:1180px;padding-top:2.35rem;padding-bottom:3rem} header[data-testid="stHeader"]{background:transparent} #MainMenu,footer,div[data-testid="stDecoration"]{display:none}
        div[data-testid="stHorizontalBlock"]:has(.lv-header){align-items:center;min-height:5.5rem;height:5.5rem;margin-bottom:.55rem}div[data-testid="stHorizontalBlock"]:has(.lv-header)>div:last-child .stButton>button{width:100%;min-height:2.625rem;white-space:nowrap}.lv-header{display:flex;align-items:center;gap:1rem;min-height:4.5rem;margin-bottom:1rem}.lv-mark{display:block;flex:0 0 5.75rem;width:5.75rem;height:4.5rem;border:0;border-radius:0;object-fit:contain;object-position:center;box-shadow:none}.lv-placeholder{display:grid;place-items:center;flex:0 0 5.75rem;width:5.75rem;height:4.5rem;border:0;font-size:2rem}.lv-title{margin:0;font-size:clamp(1.65rem,3vw,2.15rem);font-weight:720;letter-spacing:-.04em;line-height:1}.stApp .lv-subtitle{margin:.32rem 0 0;color:var(--lv-muted);font-size:.78rem;font-weight:400}
        div[data-testid="stTabs"] [data-baseweb="tab-list"]{display:flex;width:100%;gap:.35rem;margin:1.2rem 0 1.15rem;padding:.4rem;border:1px solid var(--lv-border);border-radius:.9rem;background:var(--lv-surface)}
        div[data-testid="stTabs"] [data-baseweb="tab"]{flex:1 1 0;width:25%;min-width:0;height:2.55rem;justify-content:center;padding:0 1rem;border:1px solid transparent;border-radius:.65rem;background:var(--lv-control);color:var(--lv-muted);transition:border-color 140ms ease,background 140ms ease,transform 140ms ease}
        div[data-testid="stTabs"] [data-baseweb="tab"] :is(p,span){color:var(--lv-muted)!important;-webkit-text-fill-color:var(--lv-muted)!important}
        div[data-testid="stTabs"] [data-baseweb="tab"]:hover{border-color:var(--lv-strong);background:var(--lv-hover);color:var(--lv-muted);transform:translateY(-1px)}
        div[data-testid="stTabs"] [data-baseweb="tab"]:hover :is(p,span,svg){color:var(--lv-muted)!important;fill:currentColor!important;-webkit-text-fill-color:var(--lv-muted)!important}
        div[data-testid="stTabs"] [aria-selected="true"]{border-color:var(--lv-strong);background:var(--lv-hover);color:var(--lv-muted)!important;box-shadow:0 0 0 1px var(--lv-border)}
        div[data-testid="stTabs"] [aria-selected="true"] *,div[data-testid="stTabs"] [aria-selected="true"] :is(p,span,svg),div[data-testid="stTabs"] [aria-selected="true"] [data-testid="stIconMaterial"]{color:var(--lv-muted)!important;fill:currentColor!important;-webkit-text-fill-color:var(--lv-muted)!important}
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{display:none}
        div[data-testid="stTabs"] [data-baseweb="tab-border"]{display:none}
        div[data-testid="stVerticalBlockBorderWrapper"]>div{border-color:var(--lv-border);border-radius:14px;background:var(--lv-surface);box-shadow:0 10px 30px rgba(0,0,0,.12)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero)>div{overflow:hidden;border-color:var(--lv-border);background:linear-gradient(180deg,rgba(255,255,255,.065),rgba(255,255,255,.035));box-shadow:0 14px 34px rgba(0,0,0,.25)}
        .light-card-hero{position:relative;height:8.25rem;margin:-1rem -1rem .8rem;background-color:#1d1d1d;background-position:center;background-repeat:no-repeat;background-size:cover;overflow:hidden}
        .light-card-hero::after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,10,10,.05),rgba(10,10,10,.82));pointer-events:none}
        .light-card-status{position:absolute;right:.7rem;bottom:.65rem;z-index:2;display:inline-flex;align-items:center;gap:.35rem;padding:.3rem .55rem;border:1px solid var(--lv-border);border-radius:999px;background:rgba(17,17,17,.78);backdrop-filter:blur(8px);color:var(--lv-muted);font-size:.7rem;font-weight:600}
        .light-card-status i{display:block;width:.45rem;height:.45rem;border-radius:50%;background:#666}
        .light-card-status.online i{background:#22c55e;box-shadow:0 0 10px rgba(34,197,94,.8)}
        .light-stats-row{display:flex;align-items:center;justify-content:space-between;gap:.65rem;width:calc((100% - 2rem)/3);min-height:3rem;margin-bottom:1rem;padding:.5rem .7rem;border:1px solid var(--lv-border);border-radius:.7rem;background:rgba(18,18,22,.72);box-shadow:0 8px 22px rgba(0,0,0,.18);box-sizing:border-box}
        .light-stat-card{display:flex;align-items:center;justify-content:flex-start;gap:.42rem;min-height:2rem;padding:0;border:0;background:transparent;box-shadow:none;white-space:nowrap}
        .light-stat-card .material-symbols-rounded{font-family:"Material Symbols Rounded"!important;font-weight:normal;font-style:normal;font-size:1.35rem;line-height:1;font-feature-settings:"liga";-webkit-font-feature-settings:"liga"}
        .light-stat-card .total{color:#ffbe55}.light-stat-card>div{display:flex;align-items:baseline;gap:.32rem;line-height:1}.light-stat-card strong{color:var(--lv-text);font-size:.9rem}.light-stat-card small{color:var(--lv-muted);font-size:.66rem}.status-orb{display:block;width:.72rem;height:.72rem;border-radius:50%}.status-orb.on{background:#ffbe55;box-shadow:0 0 10px rgba(255,190,85,.55)}.status-orb.online{background:#22c55e;box-shadow:0 0 12px rgba(34,197,94,.75)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) .light-meta-row{display:flex;align-items:center;justify-content:space-between;gap:.5rem;margin:-.15rem 0 .7rem;transform:translateY(-.45rem)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) .light-meta{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero)>div{position:relative}
        [class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]){position:relative!important;z-index:4!important;width:max-content!important;max-width:60%!important;margin:-7.65rem auto 3.6rem .75rem!important}
        [class*="st-key-edit_name_form_"]{position:relative!important;z-index:4!important;width:calc(100% - 1.5rem)!important;margin:-7.65rem .75rem 3.6rem!important}
        [class*="st-key-edit_name_form_"] div[data-testid="stHorizontalBlock"]{gap:.5rem!important}
        [class*="st-key-edit_name_form_"] input{background:rgba(26,26,26,.88)!important;backdrop-filter:blur(8px)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) [class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]) button{padding:.38rem .72rem!important;border:1px solid rgba(255,255,255,.14)!important;border-radius:.65rem!important;background:rgba(8,8,8,.76)!important;color:#e0e0e0!important;box-shadow:0 4px 14px rgba(0,0,0,.28)!important;backdrop-filter:blur(7px);text-shadow:0 1px 8px rgba(0,0,0,.9)!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) [class*="st-key-edit_name_on_"]:not([class*="st-key-edit_name_form_"]) button{position:relative!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) [class*="st-key-edit_name_on_"]:not([class*="st-key-edit_name_form_"]) button::after{content:"";display:block;position:absolute;top:50%;right:-1.35rem;width:.72rem;height:.72rem;border-radius:50%;background:#ffbe55;box-shadow:0 0 10px rgba(255,190,85,.55);transform:translateY(-50%)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-delete_light_"]{display:flex!important;justify-content:flex-end!important;width:100%!important;height:2.15rem!important;margin:0!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-delete_light_"] .stButton>button,div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[class*="st-key-delete_light_"] .stButton>button:hover{width:2.15rem!important;min-width:2.15rem!important;height:2.15rem!important;min-height:2.15rem!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important;color:#d8d8d8!important}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]{align-items:center!important;gap:.38rem!important}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]::before{content:"Off";color:var(--lv-muted)!important;font-size:.9rem;line-height:1}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]>div:last-child{color:var(--lv-muted)!important}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]>div:first-of-type{background-color:#484848!important}
        div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]>div:first-of-type>div{background-color:#b8b8b8!important}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) div[data-testid="stSlider"]{padding-top:.1rem}
        .light-control-label{display:flex;align-items:center;gap:.35rem;margin:.2rem 0 .25rem;color:var(--lv-text);font-size:.88rem}
        div[data-testid="stElementContainer"]:has(.light-control-label){margin-top:-.55rem;margin-bottom:.45rem}
        .light-control-label .material-symbols-rounded{font-family:"Material Symbols Rounded"!important;font-size:1rem;line-height:1;font-weight:normal;font-style:normal;font-feature-settings:"liga";-webkit-font-feature-settings:"liga"}
        div[class*="st-key-preset_color_"]{display:flex!important;justify-content:center!important}
        div[class*="st-key-preset_color_"] button{width:2.35rem!important;min-width:2.35rem!important;height:1.35rem!important;min-height:1.35rem!important;padding:0!important;border:0!important;border-radius:999px!important;box-shadow:none!important;font-size:0!important;line-height:0!important}
        div[class*="st-key-preset_color_"] button:hover{border:0!important;box-shadow:0 0 0 2px rgba(255,255,255,.18)!important;transform:scale(1.06)}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.light-card-hero) .stButton>button{min-height:2.55rem}
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.find-lights-card)>div{padding:1rem 1.15rem;border-color:var(--lv-border);background:var(--lv-surface);box-shadow:0 12px 30px rgba(0,0,0,.18),inset 0 1px 0 rgba(255,255,255,.025)}
        .find-lights-icon{display:grid;place-items:center;width:3.4rem;height:3.4rem;border:1px solid var(--lv-strong);border-radius:.85rem;background:var(--lv-control);box-shadow:0 8px 20px rgba(0,0,0,.2);transform:translateY(-.3rem)}
        .find-lights-icon .material-symbols-rounded{font-family:"Material Symbols Rounded"!important;font-weight:normal;font-style:normal;font-size:1.75rem;line-height:1;letter-spacing:normal;text-transform:none;white-space:nowrap;word-wrap:normal;direction:ltr;font-feature-settings:"liga";-webkit-font-feature-settings:"liga";background:linear-gradient(145deg,#f5f5f5 15%,#a3a3a3 55%,#ffffff 90%);background-clip:text;-webkit-background-clip:text;color:transparent!important;-webkit-text-fill-color:transparent}
        .find-lights-card h2{margin:0!important;padding:0!important;color:var(--lv-text);font-size:1.35rem;font-weight:700;letter-spacing:-.025em;line-height:1.15}
        .stApp .find-lights-card p{margin:.18rem 0 0!important;padding:0!important;color:var(--lv-muted);font-size:.68rem;line-height:1.2;white-space:nowrap}
        .st-key-scan_for_lights .stButton>button{min-height:3rem!important;border-color:var(--lv-strong)!important;background:#2b2b2b!important;background-image:none!important;font-weight:600!important;transition:border-color 140ms ease,background 140ms ease,transform 140ms ease!important}
        .st-key-scan_for_lights .stButton>button:hover{border-color:var(--lv-text)!important;background:var(--lv-hover)!important;transform:translateY(-1px)}
        .discovery-results-marker{display:none!important}
        details:has(.discovery-results-marker){margin-top:.35rem;border:1px solid var(--lv-border)!important;border-radius:.85rem!important;background:rgba(255,255,255,.025)!important}
        details:has(.discovery-results-marker)>summary{color:var(--lv-muted)!important}
        .light-card{padding:.2rem}.light-name{font-size:1.05rem;font-weight:650}.light-meta{color:var(--lv-muted);font-size:.72rem}.state-dot{display:inline-block;width:.55rem;height:.55rem;border-radius:50%;margin-right:.4rem;background:#666}.state-dot.on{background:#22c55e;box-shadow:0 0 12px #22c55e}.swatch{display:inline-block;width:1rem;height:1rem;border-radius:50%;margin-right:.35rem;vertical-align:-.15rem;border:1px solid var(--lv-border)}
        [class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]) .stButton>button,[class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]).stButton>button{justify-content:flex-start!important;width:auto!important;min-height:1.6rem!important;height:auto!important;padding:.5rem .88rem!important;border:1px solid rgba(255,255,255,.16)!important;border-radius:.7rem!important;background:rgba(38,38,38,.72)!important;color:#e0e0e0!important;box-shadow:0 4px 14px rgba(0,0,0,.26)!important;backdrop-filter:blur(8px);font-size:1.05rem!important;font-weight:650!important;text-align:left!important;text-decoration:none!important;text-shadow:0 1px 8px rgba(0,0,0,.9)!important}
        [class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]) .stButton>button:hover,[class*="st-key-edit_name_"]:not([class*="st-key-edit_name_form_"]).stButton>button:hover{color:#e0e0e0!important;text-decoration:none!important;border-color:rgba(255,255,255,.22)!important;background:rgba(44,44,44,.78)!important}
        div[class*="st-key-confirm_name_"] .stButton>button{min-width:2.5rem!important;padding:.35rem!important}
        .stButton>button{border:1px solid var(--lv-border)!important;border-radius:.65rem!important;background:var(--lv-control)!important;color:var(--lv-text)!important}.stButton>button:hover{border-color:var(--lv-strong)!important;background:var(--lv-hover)!important}
        div[data-testid="stForm"]{padding:1.1rem;border-color:var(--lv-border);border-radius:14px;background:var(--lv-surface)}
        @media(max-width:700px){.block-container{padding:.85rem .8rem 2rem}div[data-testid="stHorizontalBlock"]:has(.lv-header){flex-wrap:wrap!important}div[data-testid="stHorizontalBlock"]:has(.lv-header)>div[data-testid="stColumn"]{flex:1 1 100%!important;width:100%!important}.lv-header{flex-wrap:nowrap!important;gap:.65rem;min-width:0}.lv-header>div{min-width:0;flex:1 1 auto}.lv-placeholder,.lv-mark{flex:0 0 4.25rem;width:4.25rem;height:3.5rem}.lv-title{white-space:nowrap;font-size:clamp(1.55rem,8vw,2rem)}.lv-subtitle{display:none}.light-stats-row{width:100%}div[data-testid="stHorizontalBlock"]:has(.find-lights-card){flex-wrap:wrap!important}.find-lights-icon{width:3rem;height:3rem}.find-lights-card h2{font-size:1.1rem}.find-lights-card p{white-space:normal!important}.st-key-scan_for_lights{width:100%}}
        </style>""")
        swatch_rules = "".join(
            f'div[class*="st-key-preset_color_"][class*="_{color[1:]}"] button,div[class*="st-key-preset_color_"][class*="_{color[1:]}"] button:hover{{background-color:{color}!important;color:transparent!important;-webkit-text-fill-color:transparent!important}}'
            for color in UIConfig.PRESET_COLORS
        )
        st.html(f"<style>{swatch_rules}</style>")
