import re
import zipfile
import io
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from spellchecker import SpellChecker
from docx import Document
from openpyxl import load_workbook
from xml.etree import ElementTree as ET

try:
    from pptx import Presentation
except ModuleNotFoundError:
    Presentation = None

router = APIRouter()

spell_checker = SpellChecker(language='en')


def _require_pptx_support():
    if Presentation is None:
        raise HTTPException(status_code=500, detail="当前环境缺少 python-pptx 依赖，暂不支持 PPTX 文件处理")

MAX_SPELL_ERRORS = 100
MAX_GRAMMAR_ERRORS = 200

SING_VERBS = {"is", "was", "has", "does"}
PLUR_VERBS = {"are", "were", "have", "do"}
ALL_AUX_VERBS = SING_VERBS | PLUR_VERBS
MODAL_VERBS = {"can", "could", "may", "might", "will", "would", "shall", "should", "must"}
SING_PRON = {"he", "she", "this", "that", "someone", "anyone", "everyone", "one"}
PLUR_PRON = {"we", "they", "these", "those", "both", "many", "few"}
EXCLUDE_WORDS = {
    "guide", "system", "interface", "chapter", "section", "page", "tab",
    "range", "device", "moment", "step", "sample", "problem", "air",
    "equipment", "performance", "case", "u.s.", "us",
    "in", "to", "on", "up", "into", "with", "at", "for", "by", "from",
    "still", "briefly", "downward", "no", "now", "here", "there", "also",
    "you", "each", "it", "what", "do"
}
FULL_EXCLUDE = ALL_AUX_VERBS | MODAL_VERBS | EXCLUDE_WORDS

WHITELIST_PATTERNS = {
    "product": re.compile(r"(MGISP(?:-\d+)?(?:-Smart\s+8)?|DNBSEQ(?:-[Tt]\d+[×xX]?\d+[RSrs]?)?|MGICLab(?:-FZ\d+)?|MGI)", re.IGNORECASE),
    "brand": re.compile(r"(Qubit|Eppendorf|HamiLton|Hamilton|Invitrogen|Thermo\s+Fisher\s+Scientific|BMG\s+LABTECH|AXYGEN|Greiner\s+Bio-One|Fluostar\s+Omega)", re.IGNORECASE),
    "document_id": re.compile(r"(JB-\w+-\d+|V\d+\.\d+(?:\.\d+)*|940-\d{6}-\d{2})"),
    "term": re.compile(r"(ssCir|dsDNA|PCR|RCR|DNB|DIPSEQ|OliGreen|MPC2000|ALPS\s+50V|Pos\d+~?Pos\d+|wfex|sp960)", re.IGNORECASE),
    "domain": re.compile(r"(mgi-tech\.com|global-mgitech\.com|MGI-service@mgi-tech\.com)"),
    "scientific": re.compile(r"(E\.\s*coli|in\s+situ|in\s+vitro|in\s+vivo|et\s+al\.)", re.IGNORECASE),
    "element": re.compile(r"(H|He|Li|Be|B|C|N|O|F|Ne|Na|Mg|Al|Si|P|S|Cl|Ar|K|Ca|Sc|Ti|V|Cr|Mn|Fe|Co|Ni|Cu|Zn|Ga|Ge|As|Se|Br|Kr|Rb|Sr|Y|Zr|Nb|Mo|Tc|Ru|Rh|Pd|Ag|Cd|In|Sn|Sb|Te|I|Xe|Cs|Ba|La|Ce|Pr|Nd|Pm|Sm|Eu|Gd|Tb|Dy|Ho|Er|Tm|Yb|Lu|Hf|Ta|W|Re|Os|Ir|Pt|Au|Hg|Tl|Pb|Bi|Po|At|Rn|Fr|Ra|Ac|Th|Pa|U|Np|Pu|Am|Cm|Bk|Cf|Es|Fm|Md|No|Lr)"),
}

TECH_TERMS = {
    "ng", "mg", "kg", "ug", "pg", "fg", "ml", "ul", "nl", "pl", "fl", "dl",
    "mm", "cm", "dm", "km", "nm", "um", "pm", "fm",
    "ms", "us", "ns",
    "mol", "mmol", "umol", "nmol", "pmol", "fmol",
    "sec", "min", "hr", "hrs", "mins", "secs",
    "rpm", "rcf", "od", "rbc", "wbc",
    "bp", "kb", "mb", "gb", "kda", "mda", "da",
    "atp", "nad", "fadh", "tris", "edta", "bsa", "fbs", "dmem", "rpmi", "pbs",
    "elisa", "chip", "chipseq", "facs", "western", "blot", "wb", "ip",
    "illumina", "nanopore", "pacbio", "bgi", "qiagen", "invitrogen",
    "miseq", "hiseq", "nextseq", "novaseq", "minion", "promethion",
    "rnase", "dnase", "hek", "cho", "gfp", "yfp", "cfp", "rfp", "egfp",
    "ph", "coli",
    "qpcr", "rtpcr", "ngs", "wgs", "wes", "wts",
    "dna", "rna", "rrna", "mrna", "scrna", "cdna", "pcr", "ssdna", "dsdna", "gdna",
    "dnb", "dnbseq", "mgi", "dnbe", "dnbs", "omics", "pipetting", "biosafety",
    "extranet", "thermo", "oligo", "rxn", "qubit", "milli-q", "dnbseqtm", "qubittm",
    "mgisp", "mgiclab", "qubit", "eppendorf", "hamilton", "hamiilton",
    "bmglabtech", "axygen", "greiner", "fluostar", "omega",
    "sscir", "rcr", "dipseq", "oligreen", "mpc2000", "alps",
    "wfex", "sp960",
    "situ", "vitro", "vivo",
    "coli", "tech", "mgitech", "hs", "xte", "te",

    # 技术术语（从CSV提取）
    "abdomen",
    "aberration",
    "abort",
    "aborted",
    "accessories",
    "accuracy",
    "adapter",
    "adenine",
    "adenovirus",
    "admin",
    "aerosols",
    "agilent",
    "airdetectionsensitivity",
    "airgapdetection",
    "alarm",
    "allele",
    "alpha",
    "amphibians",
    "analyze",
    "antibody",
    "aperture",
    "api",
    "apoptosis",
    "app",
    "appendix",
    "approver",
    "approx",
    "apptitle",
    "archaea",
    "aspirate",
    "aspirateoffsetdirection",
    "aspirator",
    "assembling",
    "assess",
    "async",
    "auto",
    "autosome",
    "autostep",
    "avg",
    "bacteria",
    "baffle",
    "bai",
    "barcode",
    "barcodefilepath",
    "barcodelength",
    "base",
    "basecall",
    "basecallip",
    "baseline",
    "baygene",
    "beaker",
    "beta",
    "binuclease",
    "bioinformatics",
    "bioligo",
    "biosafety",
    "bioverse",
    "blang",
    "bonan",
    "braille",
    "bubbles",
    "buckle",
    "buret",
    "buyei",
    "buzzer",
    "calchannelcounts",
    "calibration",
    "carotid",
    "carp",
    "cartridgeinplace",
    "caster",
    "cat",
    "ccd",
    "centrifuge",
    "chastity",
    "chloroplasts",
    "chromosome",
    "chuck",
    "cine",
    "clamping",
    "class",
    "cleanfcscriptpath",
    "cleanliness",
    "cloning",
    "clotdetection",
    "clotdetectionsensitivity",
    "cnt",
    "coagulation",
    "codon",
    "collapse",
    "colony",
    "commissioning",
    "compatibility",
    "compatible",
    "compensation",
    "compensations",
    "complaint",
    "concentrator",
    "condenser",
    "conductive",
    "cone",
    "confidential",
    "config",
    "conflicting",
    "conformity",
    "congenital",
    "constraint",
    "consumable",
    "consumables",
    "contig",
    "contraindications",
    "controlboard",
    "conversion",
    "coturnserveraddr",
    "counterclockwise",
    "creep",
    "crosstalk",
    "crystal",
    "crystallization",
    "css",
    "culture",
    "cyclization",
    "cycloneseq",
    "cytoactivity",
    "cytolysis",
    "cytosine",
    "dai",
    "daur",
    "deang",
    "debris",
    "degeneracy",
    "dehumidifier",
    "deletion",
    "delta",
    "demo",
    "demulsification",
    "denaturation",
    "denature",
    "denoise",
    "derung",
    "desiccator",
    "designer",
    "detailed",
    "dia",
    "diaphragm",
    "dicot",
    "dideoxynucleotides",
    "digestion",
    "dipeptide",
    "direction",
    "disconnect",
    "disconnecting",
    "disinfectant",
    "dislodge",
    "dispense",
    "dispenseheight",
    "dispensemanner",
    "distributor",
    "dntp",
    "dog",
    "dominant",
    "dong",
    "dongle",
    "dongxiang",
    "downsampling",
    "drawer",
    "driver",
    "droplets",
    "dsdna",
    "duck",
    "duplication",
    "durability",
    "eclinkrfid",
    "electrophoresis",
    "elute",
    "emptyairoffsetofz",
    "emptyairrate",
    "endexam",
    "engineer",
    "english",
    "enhancer",
    "enrich",
    "epe",
    "epi",
    "equilibrate",
    "etc",
    "ethanol",
    "euchromatin",
    "eui",
    "evaporator",
    "ewenki",
    "exam",
    "examconclusion",
    "execute",
    "exit",
    "exiting",
    "exome",
    "exon",
    "expand",
    "expandpos",
    "extend",
    "extendtype",
    "eyepiece",
    "factory",
    "failed",
    "farther",
    "female",
    "fence",
    "figure",
    "filtered",
    "final",
    "firstspeedofz",
    "fixation",
    "fixture",
    "flatness",
    "flowcellinplace",
    "fluorometer",
    "fluorophore",
    "foci",
    "folk",
    "forceps",
    "formamide",
    "fragmentation",
    "freezer",
    "ftat",
    "fungi",
    "funnel",
    "furnace",
    "gaoshan",
    "gasket",
    "gdna",
    "gelao",
    "gender",
    "gene",
    "genewell",
    "genotype",
    "genotyping",
    "genus",
    "gin",
    "goat",
    "goose",
    "grasp",
    "grind",
    "gripper",
    "guanine",
    "guest",
    "gui",
    "gynecology",
    "hamster",
    "han",
    "hani",
    "hanshine",
    "haploid",
    "haploinsufficiency",
    "harm",
    "hazard",
    "heart",
    "hemocytometer",
    "hemolysis",
    "hemophilia",
    "heterochromatin",
    "heterozygous",
    "hikvision",
    "hollow",
    "homepage",
    "homogenize",
    "homologs",
    "homology",
    "homozygous",
    "hotplate",
    "hour",
    "housing",
    "html",
    "hui",
    "humidity",
    "hybridization",
    "hydrophilic",
    "hydrophobic",
    "idcard",
    "identity",
    "idx",
    "ignore",
    "illustration",
    "imageformat",
    "imager",
    "imageregion",
    "immunotherapy",
    "importer",
    "importing",
    "impurities",
    "inactivate",
    "incubate",
    "info",
    "ingroup",
    "inherited",
    "inhibitor",
    "initialization",
    "initialize",
    "initializing",
    "integrity",
    "interaction",
    "introduction",
    "intron",
    "invertebrate",
    "io",
    "irradiance",
    "isextend",
    "isexternalexc",
    "ismultipoint",
    "isochores",
    "isopropanol",
    "isopropyl",
    "issync",
    "isverifydata",
    "ivd",
    "jingpo",
    "jino",
    "joystick",
    "js",
    "kazak",
    "keyword",
    "kidney",
    "kilobase",
    "kingdom",
    "kirgiz",
    "labeling",
    "labware",
    "lahu",
    "landscape",
    "lane",
    "laser",
    "leukemia",
    "lever",
    "lhoba",
    "libraryid",
    "lid",
    "lifecycle",
    "lint",
    "liquidclass",
    "lisu",
    "lithography",
    "live",
    "liver",
    "locus",
    "loglevel",
    "loop",
    "loopindex",
    "lot",
    "lung",
    "lymphocyte",
    "lysozyme",
    "macroparticle",
    "magnification",
    "male",
    "malformation",
    "mammals",
    "man",
    "manage",
    "manifests",
    "manifold",
    "manufacture",
    "maonan",
    "mapping",
    "marking",
    "mask",
    "max",
    "melanoma",
    "melway",
    "membership",
    "metagenomics",
    "metaphase",
    "metatranscriptomics",
    "methylation",
    "miao",
    "microarray",
    "microchannel",
    "micrometer",
    "microorganisms",
    "micropipette",
    "microplate",
    "microsatellite",
    "microswitch",
    "microtome",
    "microvibration",
    "mindetectoffsetofz",
    "mindvision",
    "minisatellite",
    "misalignment",
    "misfocusing",
    "mission",
    "mitochondrion",
    "mixaspirateheight",
    "mixaspirateoffset",
    "mixdispenseheight",
    "mixdispenseoffset",
    "mixdispenseoffsetdirection",
    "mixemptyheight",
    "mixemptyoffset",
    "mixemptyoffsetdirection",
    "mixture",
    "modifying",
    "monba",
    "mongol",
    "monocot",
    "monosomy",
    "mortar",
    "motif",
    "msg",
    "mulao",
    "multimeter",
    "multipointinfo",
    "mutation",
    "mute",
    "naxi",
    "neurofibromatosis",
    "neuroscience",
    "never",
    "newtemplate",
    "noise",
    "normal",
    "normalization",
    "nsclc",
    "nuclease",
    "octagonal",
    "ocular",
    "offline",
    "offsetspeedofxy",
    "oligonucleotide",
    "oncogene",
    "open",
    "openpore",
    "operational",
    "operon",
    "optical",
    "optocoupler",
    "oroqen",
    "orthology",
    "os",
    "oscilloscope",
    "others",
    "outgroup",
    "outpatient",
    "oven",
    "overview",
    "pack",
    "paraconfig",
    "parafilm",
    "parallel",
    "paralogy",
    "parasite",
    "pass",
    "pathogen",
    "paused",
    "pausing",
    "pdf",
    "pedigree",
    "pellet",
    "peltier",
    "pending",
    "permeabilization",
    "personnel",
    "phantom",
    "pharynx",
    "phylogenetic",
    "phylum",
    "pickupoffsetz",
    "pierce",
    "pipette",
    "plant",
    "plasma",
    "play",
    "plunger",
    "polydactyly",
    "pooling",
    "portrait",
    "positioning",
    "positivesign",
    "postairrate",
    "poultry",
    "powder",
    "preairrate",
    "precipitates",
    "preface",
    "prepare",
    "preparing",
    "pressed",
    "preventdrop",
    "preview",
    "previous",
    "primer",
    "printer",
    "probe",
    "profilometer",
    "promoter",
    "pronucleus",
    "proposedvalue",
    "protein",
    "proteome",
    "proteomics",
    "prototyping",
    "pulse",
    "pumi",
    "pump",
    "purpose",
    "pushreport",
    "putdownoffsetz",
    "qiang",
    "quantification",
    "rabbit",
    "rack",
    "radiance",
    "radiator",
    "rat",
    "read",
    "reading",
    "ready",
    "real",
    "recessive",
    "recipe",
    "recipes",
    "red",
    "reflectance",
    "reflector",
    "refresh",
    "refrigerator",
    "registration",
    "relay",
    "reload",
    "remarks",
    "remoteaddress",
    "rename",
    "renaturation",
    "renishaw",
    "replace",
    "reserved",
    "reservoir",
    "reset",
    "reside",
    "residual",
    "restart",
    "resume",
    "resuspend",
    "retrovirus",
    "retry",
    "return",
    "rinse",
    "rod",
    "roomid",
    "roycom",
    "russia",
    "salar",
    "sata",
    "scaffold",
    "scan",
    "scanning",
    "scope",
    "script",
    "scrofa",
    "sdk",
    "sealing",
    "secondspeedofz",
    "secret",
    "segments",
    "selected",
    "sending",
    "sensitivity",
    "sent",
    "sequencer",
    "sequencing",
    "serum",
    "servertitle",
    "settempduration",
    "settimeout",
    "several",
    "severity",
    "shaker",
    "she",
    "sheep",
    "shell",
    "shutdown",
    "signalserveraddr",
    "silencer",
    "simulate",
    "simulated",
    "sipper",
    "site",
    "skirted",
    "slider",
    "softdelete",
    "solid",
    "sonographer",
    "speaker",
    "species",
    "specificity",
    "specimen",
    "spleen",
    "ssdna",
    "ssn",
    "stack",
    "startchar",
    "starteventlog",
    "starting",
    "startmicro",
    "startspeaker",
    "statement",
    "station",
    "status",
    "stepping",
    "stirrer",
    "stopcock",
    "stopeventlog",
    "stopmicro",
    "stopping",
    "stopspeaker",
    "streaks",
    "stringconst",
    "subcellular",
    "subheading",
    "subject",
    "submit",
    "substitution",
    "substrate",
    "subtyping",
    "successfully",
    "sui",
    "sum",
    "supernatant",
    "supplier",
    "swab",
    "switch",
    "syringe",
    "tajik",
    "tatar",
    "temp",
    "temperatureduration",
    "terms",
    "thaw",
    "threadlocker",
    "thymine",
    "thyroid",
    "tile",
    "timeout",
    "tips",
    "title",
    "tmp",
    "toggle",
    "tonsils",
    "toolbar",
    "tooling",
    "torque",
    "trained",
    "transcription",
    "transgene",
    "transgenic",
    "translocation",
    "translucent",
    "transmittance",
    "tray",
    "trisomy",
    "trusee",
    "trypsin",
    "ts",
    "tujia",
    "tumor",
    "typing",
    "uhrr",
    "ui",
    "unclassified",
    "uniformity",
    "unknown",
    "unspecified",
    "unused",
    "uracil",
    "username",
    "ux",
    "uygur",
    "uzbek",
    "vacuole",
    "variants",
    "vector",
    "verification",
    "verifydata",
    "verifytype",
    "vertebrate",
    "vial",
    "viscosity",
    "visibility",
    "vision",
    "voltmeter",
    "vortex",
    "vs",
    "waiting",
    "wash",
    "washing",
    "web",
    "well",
    "worklist",
    "workmode",
    "workpiece",
    "xibe",
    "yao",
    "yes",
    "yugur",
    "zang",
    "zebracall",
    "zebrafish",
    "zhuang",
}

RE_WORDS = re.compile(r"[a-zA-Z]+")
RE_MULTI_SPACE = re.compile(r"\s{2,}")
RE_MISSING_SPACE_AFTER_PUNCT = re.compile(r"(?<=[a-zA-Z])([.,;:!?])(?=[a-zA-Z])")
RE_EXTRA_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])(?=[a-zA-Z])")
RE_CASE_ERROR = re.compile(r"([.!?]\s+)([a-z]\w+)")
RE_SENTENCE = re.compile(r"[^.!?]+[.!?]")
RE_THERE_BE = re.compile(r"\bthere\s+(is|are|was|were)\b", re.IGNORECASE)
RE_AGREEMENT = re.compile(r"\b([a-zA-Z]+)\s+(is|are|was|were|has|have|does)\b", re.IGNORECASE)
RE_PRON_VERB = re.compile(r"\b(he|she)\s+([a-zA-Z]+)\b", re.IGNORECASE)
# 中文标点混入英文
RE_CHINESE_PUNCT = re.compile(r"([a-zA-Z])、([a-zA-Z])")
RE_CHINESE_DOT = re.compile(r"(?<=[a-zA-Z])。(?=[a-zA-Z])")

# 单位检查规则
RE_MICROLITER = re.compile(r"(?<=\d)ul\b|(?<=\d)uL\b")
RE_MILLILITER = re.compile(r"(?<=\d)ml\b")
RE_TIME_UNIT = re.compile(r"(?<=\d)mins\b|(?<=\d)hs\b|(?<=\d)sec\b")
RE_UNIT_CASE = re.compile(r"\b(Kg|CM|KM|ML|MG|UG|PG|FG|DL|DM|NM|PM|FM|US)\b")
RE_NUMBER_UNIT_SPACE = re.compile(r"\d+[μμmMkK][Ll]")

# 乘号检测（检测x/X代替×）
RE_MULTIPLY_SYMBOL = re.compile(r"(\d+)[xX]([A-Za-z]+)")

# 单词拆分检测
RE_WORD_SPLIT = re.compile(r"\b(desk)\s+(top)\b|\b(back)\s+(up)\b|\b(set)\s+(up)\b|\b(front)\s+(end)\b|\b(right)\s+(click)\b|\b(left)\s+(click)\b|\b(enter)\s+(key)\b|\b(delete)\s+(key)\b")

# 官网地址检查
RE_OLD_DOMAIN = re.compile(r"en\.mgi-tech\.com")

# 联系方式检查
RE_WRONG_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@(?!mgi-tech\.com)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# 风格建议模式
RE_STYLE_PATTERNS = [
    (re.compile(r"\bPlease\b", re.IGNORECASE), "Please出现在正文", "建议使用更中性的表达", "suggestion"),
    (re.compile(r"\bat\s+your\s+own\s+risk\b", re.IGNORECASE), "at your own risk", "考虑使用更正式的表述", "suggestion"),
    (re.compile(r"\bat\s+their\s+own\s+risk\b", re.IGNORECASE), "at their own risk", "考虑使用更正式的表述", "suggestion"),
]

# 语法错误模式
RE_GRAMMAR_PATTERNS = [
    (re.compile(r"\bfor\s+run\s+\w+\b", re.IGNORECASE), "for run one plate", "建议改为 for running one plate 或 for one run of", "suggestion"),
]


def is_word_in_whitelist(word, text, start, end):
    for pattern in WHITELIST_PATTERNS.values():
        if pattern.search(text, start, end + 1):
            return True
    return False

def process_text(text):
    """共享处理函数：对文本进行拼写和语法检查，优化性能"""
    text = pre_clean_lines(text)
    temp_err = []

    # --- 拼写检查：预计算唯一错词的建议，避免重复计算 ---
    word_matches = list(RE_WORDS.finditer(text))
    all_words_lower = [m.group(0).lower() for m in word_matches]
    unique_words = list(set(all_words_lower))

    unique_words_to_check = [w for w in unique_words if w not in TECH_TERMS]
    misspelled_set = spell_checker.unknown(unique_words_to_check)

    suggestion_cache = {}
    for w in misspelled_set:
        correction = spell_checker.correction(w)
        if correction:
            candidates_list = list(spell_checker.candidates(w) - {correction})[:4]
            suggestion_cache[w] = [correction] + candidates_list
        else:
            suggestion_cache[w] = []

    spell_count = 0
    for m in word_matches:
        word = m.group(0)
        w_low = word.lower()
        if w_low in suggestion_cache:
            if is_word_in_whitelist(word, text, m.start(), m.end()):
                continue
            if spell_count >= MAX_SPELL_ERRORS:
                break
            temp_err.append({
                "start": m.start(),
                "end": m.end(),
                "type": "spell",
                "severity": "general",
                "message": "拼写错误",
                "word": word,
                "suggestions": suggestion_cache[w_low]
            })
            spell_count += 1

    # --- 语法检查：限制数量避免超时，包含 word/建议字段 ---
    grammar_count = 0

    for m in RE_MULTI_SPACE.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        chunk = text[m.start():m.end()]
        if not all(c == "\n" for c in chunk):
            ctx_start = max(0, m.start() - 10)
            ctx_end = min(len(text), m.end() + 10)
            problem_text = text[m.start():m.end()]
            temp_err.append({
                "start": m.start(),
                "end": m.end(),
                "type": "grammar",
                "severity": "general",
                "message": "多余空格",
                "word": problem_text,
                "context": text[ctx_start:ctx_end],
                "suggestions": [problem_text.strip()]
            })
            grammar_count += 1

    for m in RE_MISSING_SPACE_AFTER_PUNCT.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 10)
        ctx_end = min(len(text), m.end() + 10)
        problem_text = text[m.start():m.end()]
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "grammar",
            "severity": "general",
            "message": "标点后缺失空格",
            "word": problem_text,
            "context": text[ctx_start:ctx_end],
            "suggestions": [problem_text + " "]
        })
        grammar_count += 1

    for m in RE_EXTRA_SPACE_BEFORE_PUNCT.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 10)
        ctx_end = min(len(text), m.end() + 10)
        problem_text = text[m.start():m.end()]
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "grammar",
            "severity": "general",
            "message": "标点前多余空格",
            "word": problem_text,
            "context": text[ctx_start:ctx_end],
            "suggestions": [problem_text.strip()]
        })
        grammar_count += 1

    for m in RE_CASE_ERROR.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        s = m.start() + len(m.group(1))
        e = m.end()
        problem_word = text[s:e]
        if problem_word.lower() in TECH_TERMS:
            continue
        fixed_word = problem_word.capitalize() if problem_word else problem_word
        ctx_start = max(0, m.start() - 10)
        ctx_end = min(len(text), m.end() + 10)
        temp_err.append({
            "start": s,
            "end": e,
            "type": "grammar",
            "severity": "general",
            "message": "大小写错误",
            "word": problem_word,
            "context": text[ctx_start:ctx_end],
            "suggestions": [fixed_word] if fixed_word != problem_word else []
        })
        grammar_count += 1

    # --- 中文标点混入英文检测 ---
    for m in RE_CHINESE_PUNCT.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        problem_text = text[m.start():m.end()]
        ctx_start = max(0, m.start() - 5)
        ctx_end = min(len(text), m.end() + 5)
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "grammar",
            "severity": "serious",
            "message": "中文顿号混入英文",
            "word": problem_text,
            "context": text[ctx_start:ctx_end],
            "suggestions": [m.group(1) + "," + m.group(2)]
        })
        grammar_count += 1

    for m in RE_CHINESE_DOT.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 5)
        ctx_end = min(len(text), m.end() + 5)
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "grammar",
            "severity": "serious",
            "message": "中文句号混入英文",
            "word": text[m.start():m.end()],
            "context": text[ctx_start:ctx_end],
            "suggestions": ["."]
        })
        grammar_count += 1

    # --- 单位检查 ---
    for m in RE_MICROLITER.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 5)
        ctx_end = min(len(text), m.end() + 5)
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "unit",
            "severity": "serious",
            "message": "微升单位错误",
            "word": text[m.start():m.end()],
            "context": text[ctx_start:ctx_end],
            "suggestions": ["μL"]
        })
        grammar_count += 1

    for m in RE_MILLILITER.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 5)
        ctx_end = min(len(text), m.end() + 5)
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "unit",
            "severity": "serious",
            "message": "毫升单位错误",
            "word": text[m.start():m.end()],
            "context": text[ctx_start:ctx_end],
            "suggestions": ["mL"]
        })
        grammar_count += 1

    for m in RE_TIME_UNIT.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 5)
        ctx_end = min(len(text), m.end() + 5)
        original = text[m.start():m.end()]
        suggestion = "min" if original.lower() == "mins" else ("h" if original.lower() == "hs" else "s")
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "unit",
            "severity": "serious",
            "message": "时间单位错误",
            "word": original,
            "context": text[ctx_start:ctx_end],
            "suggestions": [suggestion]
        })
        grammar_count += 1

    for m in RE_UNIT_CASE.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 5)
        ctx_end = min(len(text), m.end() + 5)
        original = text[m.start():m.end()]
        suggestion = original.lower()
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "unit",
            "severity": "general",
            "message": "单位大小写错误",
            "word": original,
            "context": text[ctx_start:ctx_end],
            "suggestions": [suggestion]
        })
        grammar_count += 1

    for m in RE_NUMBER_UNIT_SPACE.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 5)
        ctx_end = min(len(text), m.end() + 5)
        original = text[m.start():m.end()]
        suggestion = original[:-2] + " " + original[-2:]
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "unit",
            "severity": "general",
            "message": "数字与单位间缺失空格",
            "word": original,
            "context": text[ctx_start:ctx_end],
            "suggestions": [suggestion]
        })
        grammar_count += 1

    # --- 单词拆分检测 ---
    for m in RE_WORD_SPLIT.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        parts = [g for g in m.groups() if g]
        combined = "".join(parts)
        ctx_start = max(0, m.start() - 5)
        ctx_end = min(len(text), m.end() + 5)
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "format",
            "severity": "general",
            "message": "单词拆分",
            "word": text[m.start():m.end()],
            "context": text[ctx_start:ctx_end],
            "suggestions": [combined]
        })
        grammar_count += 1

    # --- 乘号检测 ---
    for m in RE_MULTIPLY_SYMBOL.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 5)
        ctx_end = min(len(text), m.end() + 5)
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "format",
            "severity": "general",
            "message": "乘号表示",
            "word": text[m.start():m.end()],
            "context": text[ctx_start:ctx_end],
            "suggestions": [m.group(1) + "×" + m.group(2)]
        })
        grammar_count += 1

    # --- 官网地址检查 ---
    for m in RE_OLD_DOMAIN.finditer(text):
        if grammar_count >= MAX_GRAMMAR_ERRORS:
            break
        ctx_start = max(0, m.start() - 10)
        ctx_end = min(len(text), m.end() + 10)
        temp_err.append({
            "start": m.start(),
            "end": m.end(),
            "type": "format",
            "severity": "serious",
            "message": "官网地址错误",
            "word": text[m.start():m.end()],
            "context": text[ctx_start:ctx_end],
            "suggestions": ["https://global-mgitech.com"]
        })
        grammar_count += 1

    # --- 语法错误模式 ---
    for pattern, msg, suggestion, severity in RE_GRAMMAR_PATTERNS:
        for m in pattern.finditer(text):
            if grammar_count >= MAX_GRAMMAR_ERRORS:
                break
            ctx_start = max(0, m.start() - 5)
            ctx_end = min(len(text), m.end() + 5)
            temp_err.append({
                "start": m.start(),
                "end": m.end(),
                "type": "grammar",
                "severity": severity,
                "message": msg,
                "word": text[m.start():m.end()],
                "context": text[ctx_start:ctx_end],
                "suggestions": [suggestion]
            })
            grammar_count += 1

    # --- 风格建议 ---
    for pattern, msg, detail, severity in RE_STYLE_PATTERNS:
        for m in pattern.finditer(text):
            if grammar_count >= MAX_GRAMMAR_ERRORS:
                break
            ctx_start = max(0, m.start() - 5)
            ctx_end = min(len(text), m.end() + 5)
            temp_err.append({
                "start": m.start(),
                "end": m.end(),
                "type": "style",
                "severity": severity,
                "message": msg,
                "word": text[m.start():m.end()],
                "context": text[ctx_start:ctx_end],
                "suggestions": []
            })
            grammar_count += 1

    run_grammar(text, temp_err)

    temp_err.sort(key=lambda x: x["start"])

    unique_err = []
    last_s = -1
    for item in temp_err:
        if item["start"] != last_s:
            unique_err.append(item)
            last_s = item["start"]

    final_spell = sum(1 for item in unique_err if item["type"] == "spell")
    final_grammar = len(unique_err) - final_spell

    return {
        "errors": unique_err,
        "spell_count": final_spell,
        "grammar_count": final_grammar,
        "total_count": len(unique_err),
        "text": text
    }


def is_noun_singular(word: str) -> bool:
    w = word.lower().strip()
    if w in SING_PRON:
        return True
    if w in PLUR_PRON:
        return False
    if w in FULL_EXCLUDE:
        return True
    if w.endswith(("s", "es", "ies", "ves")):
        return False
    return True


def get_nearest_noun_after_be(sent: str) -> str:
    part = re.sub(r"\s+and\s+.+", "", sent, flags=re.IGNORECASE)
    words = part.strip().split()
    for w in words:
        w_low = w.lower()
        if w_low not in FULL_EXCLUDE:
            return w
    return ""


def check_there_be(sent: str, offset: int, full_text: str, err_list):
    for m in RE_THERE_BE.finditer(sent):
        verb = m.group(1).lower()
        after_be = sent[m.end():]
        nearest_noun = get_nearest_noun_after_be(after_be)
        if not nearest_noun:
            continue
        sub_sing = is_noun_singular(nearest_noun)
        verb_sing = verb in SING_VERBS
        if (sub_sing and not verb_sing) or (not sub_sing and verb_sing):
            s = offset + m.start(1)
            e = offset + m.end(1)
            err_list.append({"start": s, "end": e, "type": "grammar", "severity": "general", "message": "主谓不一致"})


def check_normal_agreement(sent: str, offset: int, full_text: str, err_list):
    for m in RE_AGREEMENT.finditer(sent):
        sub = m.group(1).lower()
        verb = m.group(2).lower()
        if sent.lower().startswith("there "):
            continue
        if sub in FULL_EXCLUDE:
            continue
        sub_sing = is_noun_singular(sub)
        verb_sing = verb in SING_VERBS
        if (sub_sing and not verb_sing) or (not sub_sing and verb_sing):
            s = offset + m.start(2)
            e = offset + m.end(2)
            err_list.append({"start": s, "end": e, "type": "grammar", "severity": "general", "message": "主谓不一致"})

    for m in RE_PRON_VERB.finditer(sent):
        verb = m.group(2).lower()
        if verb in ALL_AUX_VERBS or verb in MODAL_VERBS or verb in FULL_EXCLUDE:
            continue
        if not verb.endswith(("s", "es")):
            s = offset + m.start(2)
            e = offset + m.end(2)
            err_list.append({"start": s, "end": e, "type": "grammar", "severity": "general", "message": "主谓不一致"})


def run_grammar(text: str, err_list):
    for m in RE_SENTENCE.finditer(text):
        s_txt = m.group(0)
        s_off = m.start()
        check_there_be(s_txt, s_off, text, err_list)
        check_normal_agreement(s_txt, s_off, text, err_list)


def read_dita(f):
    try:
        tree = ET.parse(f)
        root = tree.getroot()
        buf = []
        for elem in root.iter():
            if elem.text and elem.text.strip():
                buf.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                buf.append(elem.tail.strip())
        return "\n".join(buf)
    except Exception:
        return ""


def read_idml(f):
    try:
        buf = []
        with zipfile.ZipFile(f, "r") as zf:
            for name in zf.namelist():
                name_lower = name.lower()
                if not (name_lower.startswith("stories/") and name_lower.endswith(".xml")):
                    continue
                try:
                    with zf.open(name) as xml_file:
                        tree = ET.parse(xml_file)
                        root = tree.getroot()
                        for elem in root.iter():
                            tag = elem.tag.rsplit('}', 1)[-1] if isinstance(elem.tag, str) else ''
                            if tag != 'Content':
                                continue
                            if elem.text and elem.text.strip():
                                text = elem.text.strip()
                                if len(text) > 1:
                                    buf.append(text)
                except Exception:
                    continue
        return "\n".join(buf)
    except Exception:
        return ""


def pre_clean_lines(text):
    lines = text.splitlines()
    res = []
    blank = 0
    for ln in lines:
        if not ln.strip():
            blank += 1
        else:
            if blank < 3:
                res += [""] * blank
            blank = 0
            res.append(ln)
    if 0 < blank < 3:
        res += [""] * blank
    return "\n".join(res)


def extract_text_from_file(file: UploadFile):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    content = file.file.read()

    if ext == ".zip":
        txt = ""
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                name_lower = name.lower()
                try:
                    with zf.open(name) as f:
                        file_content = f.read()
                        if name_lower.endswith(".dita") or name_lower.endswith(".xml"):
                            bio = io.BytesIO(file_content)
                            dita_content = read_dita(bio)
                            if dita_content.strip():
                                txt += f"--- {name} ---\n{dita_content}\n\n"
                        elif name_lower.endswith(".md"):
                            md_content = file_content.decode('utf-8', errors='ignore')
                            if md_content.strip():
                                txt += f"--- {name} ---\n{md_content}\n\n"
                        elif name_lower.endswith(".idml"):
                            bio = io.BytesIO(file_content)
                            idml_content = read_idml(bio)
                            if idml_content.strip():
                                txt += f"--- {name} ---\n{idml_content}\n\n"
                        elif name_lower.endswith(".txt"):
                            txt += f"--- {name} ---\n{file_content.decode('utf-8', errors='ignore')}\n\n"
                        elif name_lower.endswith(".docx"):
                            bio = io.BytesIO(file_content)
                            doc = Document(bio)
                            doc_text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())
                            if doc_text.strip():
                                txt += f"--- {name} ---\n{doc_text}\n\n"
                        elif name_lower.endswith(".xlsx"):
                            bio = io.BytesIO(file_content)
                            wb = load_workbook(bio, read_only=True)
                            ws = wb.active
                            xlsx_text = ""
                            for row in ws.iter_rows(values_only=True):
                                row_text = "\t".join(str(cell) for cell in row if cell is not None)
                                if row_text.strip():
                                    xlsx_text += row_text + "\n"
                            if xlsx_text.strip():
                                txt += f"--- {name} ---\n{xlsx_text}\n\n"
                        elif name_lower.endswith(".pptx"):
                            _require_pptx_support()
                            bio = io.BytesIO(file_content)
                            prs = Presentation(bio)
                            pptx_text = ""
                            for slide in prs.slides:
                                for shape in slide.shapes:
                                    if hasattr(shape, "text") and shape.text.strip():
                                        pptx_text += shape.text + "\n"
                            if pptx_text.strip():
                                txt += f"--- {name} ---\n{pptx_text}\n\n"
                except Exception as e:
                    continue
        return txt
    elif ext == ".dita" or ext == ".xml":
        bio = io.BytesIO(content)
        return read_dita(bio)
    elif ext == ".md":
        return content.decode("utf-8", errors="ignore")
    elif ext == ".idml":
        bio = io.BytesIO(content)
        return read_idml(bio)
    elif ext == ".txt":
        return content.decode("utf-8", errors="ignore")
    elif ext == ".docx":
        bio = io.BytesIO(content)
        doc = Document(bio)
        return "\n".join(para.text for para in doc.paragraphs)
    elif ext == ".xlsx":
        bio = io.BytesIO(content)
        wb = load_workbook(bio, read_only=True)
        ws = wb.active
        txt = ""
        for row in ws.iter_rows(values_only=True):
            row_text = " ".join(str(cell) for cell in row if cell is not None)
            txt += row_text + "\n"
        return txt
    elif ext == ".pptx":
        _require_pptx_support()
        bio = io.BytesIO(content)
        ppt = Presentation(bio)
        txt = ""
        for slide in ppt.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    txt += shape.text + "\n"
        return txt
    else:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")


class SpellCheckRequest(BaseModel):
    text: str


@router.post("/check", summary="检查文本拼写语法")
async def check_spell(request: SpellCheckRequest):
    if not request.text.strip():
        return {"errors": [], "spell_count": 0, "grammar_count": 0, "total_count": 0, "text": ""}
    return process_text(request.text)


@router.post("/upload", summary="上传文件并检查拼写语法")
async def upload_and_check(file: UploadFile = File(...)):
    try:
        text = extract_text_from_file(file)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件读取失败: {str(e)}")

    if not text.strip():
        return {"errors": [], "spell_count": 0, "grammar_count": 0, "total_count": 0, "text": "", "filename": file.filename}

    result = process_text(text)
    result["filename"] = file.filename
    return result


@router.post("/add-word", summary="添加自定义单词到词典")
async def add_custom_word(word: str):
    word = word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="单词不能为空")
    spell_checker.word_frequency.load_words([word])
    return {"message": f"已添加单词: {word}"}


@router.post("/import-dict", summary="导入词典文件")
async def import_dict(file: UploadFile = File(...)):
    content = await file.read()
    lines = content.decode("utf-8").splitlines()
    words_to_add = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words_to_add.append(line)
    spell_checker.word_frequency.load_words(words_to_add)
    return {"message": f"成功导入 {len(words_to_add)} 个单词"}


@router.get("/export-dict", summary="导出自定义词典")
async def export_dict():
    words = []
    for w in spell_checker.word_frequency:
        words.append(w)
    return {"words": words}
