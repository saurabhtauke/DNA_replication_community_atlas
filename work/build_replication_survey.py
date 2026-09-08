#!/usr/bin/env python3
"""Build an auditable DNA-replication researcher survey from OpenAlex metadata."""

from __future__ import annotations

import csv
import json
import math
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
RAW = ROOT / "work" / "openalex_cache"
OUT.mkdir(exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
AS_OF = "2026-09-08"
RECENT_START = "2021-01-01"

# Curated for breadth across replication initiation, replisomes, fork stress/repair,
# genome-wide replication, chromatin inheritance, and single-molecule mechanisms.
# The first 50 are ranking-eligible. Two requested early-career researchers are
# additional entries, not forced into the PI ranking.
ROSTER = [
 # name, expected institution fragment, career label, techniques, subfields, eligible
 ("John F. X. Diffley", "Crick", "established giant", "bulk biochemistry; cryo-EM; yeast genetics", "eukaryotic initiation; origin firing; replisome reconstitution", 1),
 ("Michael O'Donnell", "Rockefeller", "established giant", "bulk biochemistry; structural biology; single-molecule", "replisome; sliding clamps; DNA polymerases", 1),
 ("Bruce Stillman", "Cold Spring Harbor", "established giant", "bulk biochemistry; cell biology; genomics", "ORC; licensing; chromatin replication", 1),
 ("Stephen P. Bell", "MIT", "established giant", "bulk biochemistry; cryo-EM; yeast genetics", "origin licensing; MCM loading; initiation", 1),
 ("Johannes C. Walter", "Harvard", "current leader", "Xenopus extracts; bulk biochemistry; cell biology", "replication-coupled repair; fork protection; termination", 1),
 ("Karim Labib", "Dundee", "current leader", "yeast genetics; bulk biochemistry; proteomics", "CMG; replisome; termination; protein degradation", 1),
 ("Alessandro Costa", "Crick", "rising/recent leader", "cryo-EM; structural biology; bulk biochemistry", "CMG; initiation; origin unwinding", 1),
 ("David Cortez", "Vanderbilt", "current leader", "cell biology; proteomics; genomics", "replication stress; fork protection; ATR signaling", 1),
 ("James M. Berger", "Johns Hopkins", "established giant", "cryo-EM; crystallography; bulk biochemistry", "replicative helicases; initiators; topoisomerases", 1),
 ("David M. Gilbert", "San Diego Biomedical", "established giant", "sequencing/genomics; cell biology; imaging", "replication timing; nuclear organization; origins", 1),
 ("Julian J. Blow", "Dundee", "established giant", "Xenopus extracts; cell biology; bulk biochemistry", "licensing; dormant origins; replication stress", 1),
 ("Anja Groth", "Copenhagen", "current leader", "cell biology; sequencing/genomics; proteomics", "chromatin inheritance; histone recycling; fork biology", 1),
 ("Thanos D. Halazonetis", "Geneva", "established giant", "cell biology; genomics; imaging", "oncogene-induced replication stress; DNA damage response; cancer", 1),
 ("Daniel Durocher", "Lunenfeld", "current leader", "cell biology; functional genomics; proteomics", "DNA repair; replication stress; genome stability", 1),
 ("Oscar Fernandez-Capetillo", "CNIO", "current leader", "mouse genetics; cell biology; functional genomics", "ATR; replication stress; cancer", 1),
 ("Massimo Lopes", "Zurich", "current leader", "electron microscopy; cell biology; DNA fiber assays", "fork remodeling; replication stress; nascent DNA", 1),
 ("Dana Branzei", "IFOM", "current leader", "yeast genetics; cell biology; biochemistry", "template switching; sister chromatid junctions; fork repair", 1),
 ("Xiaolan Zhao", "Sloan Kettering", "current leader", "yeast genetics; biochemistry; proteomics", "SUMO; replication stress; genome stability", 1),
 ("Lee Zou", "Massachusetts General", "current leader", "cell biology; biochemistry; genomics", "ATR checkpoint; replication stress; fork protection", 1),
 ("Karl E. Duderstadt", "Max Planck", "rising/recent leader", "single-molecule; cryo-EM; bulk biochemistry", "replisome dynamics; helicase-polymerase coupling", 1),
 ("Nynke H. Dekker", "Delft", "current leader", "single-molecule; magnetic tweezers; optical tweezers", "replisome dynamics; helicases; topological stress", 1),
 ("Shixin Liu", "Rockefeller", "rising/recent leader", "single-molecule; fluorescence imaging; biochemistry", "replication initiation; helicases; replisome dynamics", 1),
 ("Hasan Yardimci", "Crick", "rising/recent leader", "single-molecule; Xenopus extracts; imaging", "replication barriers; fork collisions; DNA-protein crosslinks", 1),
 ("Antoine M. van Oijen", "Wollongong", "current leader", "single-molecule; fluorescence imaging; microfluidics", "replisome dynamics; replication restart; bacterial/eukaryotic replication", 1),
 ("Eric C. Greene", "Columbia", "current leader", "single-molecule; DNA curtains; fluorescence imaging", "protein-DNA interactions; homologous recombination; replication conflicts", 1),
 ("Maria Spies", "Iowa", "current leader", "single-molecule; biochemistry; structural biology", "helicases; fork repair; DNA damage tolerance", 1),
 ("Kenneth J. Marians", "Sloan Kettering", "established giant", "bulk biochemistry; replisome reconstitution", "bacterial replication; fork restart; helicases", 1),
 ("Nicholas Rhind", "UMass", "current leader", "sequencing/genomics; yeast genetics; computational biology", "replication timing; origins; checkpoint", 1),
 ("Conrad A. Nieduszynski", "Earlham", "current leader", "sequencing/genomics; computational biology; yeast genetics", "replication origins; replication timing; genome evolution", 1),
 ("Philippe Pasero", "Montpellier", "current leader", "DNA fiber assays; cell biology; yeast genetics", "replication stress; fork protection; R-loops", 1),
 ("Etienne Schwob", "Montpellier", "current leader", "yeast genetics; sequencing/genomics; cell biology", "origin firing; replication timing; genome stability", 1),
 ("Domenico Maiorano", "Montpellier", "current leader", "cell biology; Xenopus extracts; mouse models", "licensing; replication stress; development", 1),
 ("Juan Mendez", "CNIO", "current leader", "cell biology; DNA fiber assays; proteomics", "licensing; replisome; replication stress", 1),
 ("Christian Speck", "Imperial", "current leader", "bulk biochemistry; cryo-EM; single-molecule", "MCM loading; licensing; initiation", 1),
 ("Luca Pellegrini", "Cambridge", "current leader", "crystallography; cryo-EM; bulk biochemistry", "replisome structure; Pol alpha-primase; fork protection", 1),
 ("Agnieszka Gambus", "Birmingham", "rising/recent leader", "proteomics; cell biology; biochemistry", "human replisome; termination; fork protection", 1),
 ("Madalena Tarsounas", "Oxford", "current leader", "cell biology; imaging; DNA fiber assays", "homologous recombination; fork protection; BRCA", 1),
 ("Grant W. Brown", "Toronto", "current leader", "yeast genetics; functional genomics; cell biology", "replication stress; genome instability; checkpoint", 1),
 ("Rodney Rothstein", "Columbia", "established giant", "yeast genetics; imaging; genomics", "homologous recombination; replication repair; genome stability", 1),
 ("Susan M. Gasser", "Lausanne", "established giant", "yeast genetics; imaging; genomics", "nuclear organization; replication stress; chromatin", 1),
 ("Hiroyuki Araki", "National Institute of Genetics", "established giant", "yeast genetics; bulk biochemistry", "replication initiation; polymerases; replisome assembly", 1),
 ("Hideo Masai", "Tokyo Metropolitan", "established giant", "bulk biochemistry; cell biology; genomics", "DDK/Cdc7; initiation; replication timing", 1),
 ("Katsuhiko Shirahige", "Tokyo", "current leader", "sequencing/genomics; chromosome conformation; cell biology", "cohesion; replication; genome organization", 1),
 ("Zhiguo Zhang", "Columbia", "current leader", "cell biology; genomics; proteomics", "epigenetic inheritance; histone recycling; DNA replication", 1),
 ("Peter M. Burgers", "Washington University", "established giant", "bulk biochemistry; yeast genetics", "DNA polymerases; PCNA; Okazaki fragments", 1),
 ("Marc S. Wold", "Iowa", "established giant", "bulk biochemistry; structural biology; cell biology", "RPA; replication stress; DNA repair", 1),
 ("Lorena S. Beese", "Duke", "established giant", "crystallography; structural biology; biochemistry", "DNA polymerases; fidelity; translesion synthesis", 1),
 ("Samir M. Hamdan", "King Abdullah", "current leader", "single-molecule; fluorescence imaging; bulk biochemistry", "replisome dynamics; helicases; replication-coupled repair", 1),
 ("Marcus B. Smolka", "Cornell", "current leader", "proteomics; phosphoproteomics; yeast genetics", "replication stress; checkpoint signaling; genome stability", 1),
 ("Duncan J. Smith", "New York University", "rising/recent leader", "sequencing/genomics; yeast genetics; computational biology", "replication-transcription conflicts; fork directionality", 1),
 ("Xingzhi Xu", "Shenzhen", "current leader", "cell biology; proteomics; functional genomics", "replication stress; DNA damage signaling; genome stability", 1),
 ("Jacob S. Lewis", "Wollongong", "additional requested researcher", "single-molecule; fluorescence imaging; bulk biochemistry", "replisome dynamics; polymerase exchange", 0),
 ("Lisanne Spenkelink", "Wollongong", "additional requested researcher", "single-molecule; fluorescence imaging; microfluidics", "replisome dynamics; replication kinetics", 0),
]

# Second-pass expansion to an exact 100-person ranked roster. Tom Miller is kept
# as an additional requested researcher because the selected profile is an active
# replication researcher but not clearly an independent PI in the source record.
ROSTER += [
 ("Joseph T. P. Yeeles", "MRC Laboratory of Molecular Biology", "rising/recent leader", "bulk biochemistry; replisome reconstitution; cryo-EM", "replisome; initiation; termination", 1),
 ("Tom Deegan", "Edinburgh", "rising/recent leader", "bulk biochemistry; yeast genetics; cell biology", "replisome; replication stress; DNA repair", 1),
 ("Christoph F. Kurat", "Bayreuth", "rising/recent leader", "yeast genetics; genomics; cell biology", "chromatin replication; origin firing; genome stability", 1),
 ("Niels Mailand", "Copenhagen", "current leader", "cell biology; proteomics; functional genomics", "replication stress; DNA repair; fork protection", 1),
 ("Claus Storgaard Sørensen", "Copenhagen", "current leader", "cell biology; DNA fiber assays; proteomics", "replication stress; fork protection; checkpoint", 1),
 ("Ian D. Hickson", "Copenhagen", "established giant", "bulk biochemistry; cell biology; single-molecule", "helicases; replication stress; genome stability", 1),
 ("Puck Knipscheer", "Hubrecht", "current leader", "Xenopus extracts; bulk biochemistry; cell biology", "replication-coupled repair; DNA-protein crosslinks; fork protection", 1),
 ("Sarah A. E. Lambert", "Institut Curie", "current leader", "yeast genetics; genomics; cell biology", "replication stress; fork restart; difficult-to-replicate DNA", 1),
 ("Marco Foiani", "IFOM", "established giant", "yeast genetics; cell biology; genomics", "replication stress; checkpoint; genome stability", 1),
 ("Marco Muzi-Falconi", "Milan", "current leader", "yeast genetics; cell biology; biochemistry", "replication stress; checkpoint; DNA repair", 1),
 ("Andrés Aguilera", "Seville", "established giant", "yeast genetics; genomics; cell biology", "replication-transcription conflicts; R-loops; genome stability", 1),
 ("Angelos Constantinou", "Montpellier", "current leader", "cell biology; bulk biochemistry; DNA fiber assays", "fork protection; homologous recombination; replication stress", 1),
 ("Wojciech Niedzwiedz", "Oxford", "current leader", "cell biology; proteomics; DNA fiber assays", "fork protection; Fanconi anemia; replication stress", 1),
 ("Simon J. Boulton", "Crick", "established giant", "genetics; cell biology; proteomics", "DNA repair; replication stress; genome stability", 1),
 ("Stephen C. West", "Crick", "established giant", "bulk biochemistry; structural biology; cell biology", "homologous recombination; fork repair; genome stability", 1),
 ("Jessica A. Downs", "Cancer Research", "current leader", "cell biology; yeast genetics; proteomics", "chromatin; DNA repair; replication stress", 1),
 ("Steve P. Jackson", "Cambridge", "established giant", "cell biology; proteomics; functional genomics", "DNA damage response; replication stress; genome stability", 1),
 ("Keith W. Caldecott", "Sussex", "established giant", "cell biology; biochemistry; genetics", "DNA repair; replication-associated breaks; genome stability", 1),
 ("Fumiko Esashi", "Oxford", "current leader", "cell biology; biochemistry; imaging", "homologous recombination; fork protection; BRCA", 1),
 ("Matthew C. Whitby", "Oxford", "current leader", "yeast genetics; bulk biochemistry; cell biology", "fork restart; homologous recombination; replication stress", 1),
 ("Peter McGlynn", "York", "current leader", "bulk biochemistry; bacterial genetics; single-molecule", "bacterial replication; fork restart; replication-transcription conflicts", 1),
 ("Heath Murray", "Newcastle", "rising/recent leader", "bacterial genetics; cell biology; genomics", "bacterial replication; origin regulation; replisome", 1),
 ("Stephan Uphoff", "Oxford", "rising/recent leader", "single-molecule; fluorescence imaging; bacterial genetics", "replication stress; mutagenesis; bacterial replication", 1),
 ("David Rueda", "Imperial", "current leader", "single-molecule; fluorescence imaging; biochemistry", "DNA repair; helicases; replication dynamics", 1),
 ("Stephen C. Kowalczykowski", "California Davis", "established giant", "single-molecule; bulk biochemistry; fluorescence imaging", "homologous recombination; fork repair; helicases", 1),
 ("Sue Jinks-Robertson", "Duke", "established giant", "yeast genetics; genomics; molecular genetics", "replication-transcription conflicts; mutagenesis; genome stability", 1),
 ("Lorraine S. Symington", "Columbia", "established giant", "yeast genetics; bulk biochemistry; genomics", "homologous recombination; fork repair; DNA repair", 1),
 ("James E. Haber", "Brandeis", "established giant", "yeast genetics; genomics; cell biology", "DNA double-strand break repair; replication repair; homologous recombination", 1),
 ("Richard D. Kolodner", "California San Diego", "established giant", "genetics; genomics; bulk biochemistry", "mismatch repair; genome instability; replication fidelity", 1),
 ("Thomas D. Petes", "Duke", "established giant", "yeast genetics; genomics; molecular genetics", "replication-associated recombination; genome instability; DNA repair", 1),
 ("Graham C. Walker", "MIT", "established giant", "bacterial genetics; biochemistry; structural biology", "translesion synthesis; DNA damage tolerance; bacterial replication", 1),
 ("Susan T. Lovett", "Brandeis", "established giant", "bacterial genetics; genomics; biochemistry", "fork repair; replication restart; mutagenesis", 1),
 ("Houra Merrikh", "Vanderbilt", "current leader", "bacterial genetics; genomics; cell biology", "replication-transcription conflicts; bacterial replication; genome evolution", 1),
 ("Alessandro Vindigni", "Washington University", "current leader", "DNA fiber assays; electron microscopy; cell biology", "fork remodeling; replication stress; fork protection", 1),
 ("Maria Jasin", "Sloan Kettering", "established giant", "cell biology; mouse genetics; genome engineering", "homologous recombination; replication repair; genome stability", 1),
 ("Titia de Lange", "Rockefeller", "established giant", "cell biology; mouse genetics; imaging", "telomere replication; fork protection; chromosome ends", 1),
 ("Agnel Sfeir", "Sloan Kettering", "current leader", "cell biology; genomics; mouse genetics", "telomere replication; genome stability; replication stress", 1),
 ("Roger A. Greenberg", "Pennsylvania", "current leader", "cell biology; proteomics; functional genomics", "DNA repair; replication stress; BRCA", 1),
 ("Alberto Ciccia", "Columbia", "current leader", "functional genomics; cell biology; proteomics", "replication stress; DNA repair; fork protection", 1),
 ("Stephen J. Elledge", "Harvard", "established giant", "functional genomics; cell biology; proteomics", "DNA damage response; replication stress; checkpoint", 1),
 ("Bik-Kwoon Tye", "Hong Kong University of Science and Technology", "established giant", "yeast genetics; bulk biochemistry; genomics", "MCM helicase; origin licensing; chromatin", 1),
 ("Yuanliang Zhai", "Hong Kong University of Science and Technology", "rising/recent leader", "cryo-EM; structural biology; bulk biochemistry", "MCM loading; origin licensing; replisome structure", 1),
 ("Huilin Li", "Van Andel", "current leader", "cryo-EM; structural biology; biochemistry", "replisome structure; helicases; origin licensing", 1),
 ("Tatsuro S. Takahashi", "Kyushu", "current leader", "cell biology; Xenopus extracts; biochemistry", "origin licensing; initiation; replication timing", 1),
 ("Akira Shinohara", "Osaka", "established giant", "genetics; cell biology; biochemistry", "homologous recombination; fork repair; genome stability", 1),
 ("Andrew J. Deans", "St Vincent", "current leader", "cell biology; functional genomics; biochemistry", "Fanconi anemia; DNA crosslink repair; replication stress", 1),
 ("Ian Grainge", "New South Wales", "current leader", "single-molecule; bacterial genetics; biochemistry", "fork restart; replication termination; bacterial replication", 1),
 ("Uttam Surana", "Molecular and Cell Biology", "established giant", "yeast genetics; cell biology; genomics", "cell-cycle control; replication initiation; checkpoint", 1),
 ("Primo Schär", "Basel", "current leader", "cell biology; genetics; biochemistry", "DNA repair; replication fidelity; genome stability", 1),
 ("Thomas C. R. Miller", "Copenhagen", "additional requested researcher", "cryo-EM; electron microscopy; computational structural biology", "replisome structure; origin regulation; helicases", 0),
]

ALIASES = {
    "Stephen P. Bell": ["Stephen Bell"], "Johannes C. Walter": ["Johannes Walter"],
    "Karl E. Duderstadt": ["Karl Duderstadt"], "Nynke H. Dekker": ["Nynke Dekker"],
    "Antoine M. van Oijen": ["Antoine van Oijen"], "Nicholas Rhind": ["Nick Rhind"],
    "Conrad A. Nieduszynski": ["Conrad Nieduszynski"], "Juan Mendez": ["Juan Méndez"],
    "Peter M. Burgers": ["Peter Burgers"], "Marc S. Wold": ["Marc Wold"],
    "Lorena S. Beese": ["Lorena Beese"], "Duncan J. Smith": ["Duncan Smith"],
    "Jacob S. Lewis": ["Jacob Lewis"],
}

# Known ambiguous/split profiles pinned after manual inspection of titles and affiliations.
MANUAL_AUTHOR_IDS = {
    "Michael O'Donnell": "A5051770888",
    "Kenneth J. Marians": "A5068066930",
    "Zhiguo Zhang": "A5100363356",
    "Lisanne Spenkelink": "A5039468934",
    "Joseph T. P. Yeeles": "A5089523004",
    "Tom Deegan": "A5079736311",
    "Christoph F. Kurat": "A5022849727",
    "Thomas C. R. Miller": "A5035239553",
    "Steve P. Jackson": "A5061795154",
    "Huilin Li": "A5100330148",
    "Niels Mailand": "A5063679562",
    "Wojciech Niedzwiedz": "A5007992721",
    "Akira Shinohara": "A5114375350",
    "Hideo Masai": "A5082081122",
}

RELEVANCE = re.compile(
    r"replic|replisom|replication fork|origin firing|origin licensing|MCM|CMG|helicase|"
    r"DNA polymerase|polymerase|PCNA|RPA|Okazaki|ATR|checkpoint|fork protection|"
    r"fork restart|fork remodeling|chromatin inheritance|histone recycling|replication timing|"
    r"template switch|topoisomerase|telomere replication|cohesion|DNA-protein crosslink|"
    r"R-loop|translesion|mutagenesis|DNA synthesis|sliding clamp",
    re.I,
)

COUNTRY_NAMES = {"US":"United States", "GB":"United Kingdom", "DE":"Germany", "NL":"Netherlands", "DK":"Denmark", "ES":"Spain", "IT":"Italy", "CH":"Switzerland", "FR":"France", "CA":"Canada", "JP":"Japan", "AU":"Australia", "SE":"Sweden", "AT":"Austria", "BE":"Belgium", "FI":"Finland", "NO":"Norway", "IE":"Ireland", "CN":"China"}
CONTINENT = {"US":"North America", "CA":"North America", "GB":"Europe", "DE":"Europe", "NL":"Europe", "DK":"Europe", "ES":"Europe", "IT":"Europe", "CH":"Europe", "FR":"Europe", "SE":"Europe", "AT":"Europe", "BE":"Europe", "FI":"Europe", "NO":"Europe", "IE":"Europe", "JP":"Asia", "CN":"Asia", "AU":"Oceania"}

# Manual corrections where OpenAlex's first "last known" institution is a secondary
# affiliation, consortium address, funder (HHMI), or an obvious metadata collision.
# Each correction includes an institutional page/domain for human rechecking.
CURATED_AFFILIATIONS = {
 "Lee Zou": ("Massachusetts General Hospital / Harvard Medical School", "Boston", "United States", "North America", "https://www.massgeneral.org/"),
 "Johannes C. Walter": ("Harvard Medical School", "Boston", "United States", "North America", "https://hms.harvard.edu/"),
 "Daniel Durocher": ("Lunenfeld-Tanenbaum Research Institute", "Toronto", "Canada", "North America", "https://www.lunenfeld.ca/"),
 "Philippe Pasero": ("Institute of Human Genetics, CNRS / University of Montpellier", "Montpellier", "France", "Europe", "https://igh.cnrs.fr/"),
 "Michael O'Donnell": ("The Rockefeller University / HHMI", "New York", "United States", "North America", "https://www.rockefeller.edu/"),
 "Katsuhiko Shirahige": ("University of Tokyo", "Tokyo", "Japan", "Asia", "https://www.u-tokyo.ac.jp/"),
 "Xiaolan Zhao": ("Memorial Sloan Kettering Cancer Center", "New York", "United States", "North America", "https://www.mskcc.org/"),
 "Anja Groth": ("BRIC, University of Copenhagen", "Copenhagen", "Denmark", "Europe", "https://www.bric.ku.dk/"),
 "Zhiguo Zhang": ("Columbia University", "New York", "United States", "North America", "https://www.columbia.edu/"),
 "Xingzhi Xu": ("Shenzhen University Health Science Center", "Shenzhen", "China", "Asia", "https://med.szu.edu.cn/"),
 "Oscar Fernandez-Capetillo": ("Spanish National Cancer Research Centre (CNIO)", "Madrid", "Spain", "Europe", "https://www.cnio.es/"),
 "Dana Branzei": ("IFOM, the FIRC Institute of Molecular Oncology", "Milan", "Italy", "Europe", "https://www.ifom.eu/"),
 "Stephen P. Bell": ("Massachusetts Institute of Technology / HHMI", "Cambridge", "United States", "North America", "https://biology.mit.edu/"),
 "Samir M. Hamdan": ("King Abdullah University of Science and Technology (KAUST)", "Thuwal", "Saudi Arabia", "Asia", "https://www.kaust.edu.sa/"),
 "Antoine M. van Oijen": ("University of Wollongong", "Wollongong", "Australia", "Oceania", "https://www.uow.edu.au/"),
 "Agnieszka Gambus": ("University of Birmingham", "Birmingham", "United Kingdom", "Europe", "https://www.birmingham.ac.uk/"),
 "Domenico Maiorano": ("Institute of Human Genetics, CNRS / University of Montpellier", "Montpellier", "France", "Europe", "https://igh.cnrs.fr/"),
 "Christian Speck": ("Imperial College London", "London", "United Kingdom", "Europe", "https://www.imperial.ac.uk/"),
 "Karl E. Duderstadt": ("Max Planck Institute of Biochemistry", "Martinsried", "Germany", "Europe", "https://www.biochem.mpg.de/"),
 "Nynke H. Dekker": ("Delft University of Technology", "Delft", "Netherlands", "Europe", "https://www.tudelft.nl/"),
 "Etienne Schwob": ("Institute of Molecular Genetics of Montpellier, CNRS / University of Montpellier", "Montpellier", "France", "Europe", "https://www.igmm.cnrs.fr/"),
 "Shixin Liu": ("The Rockefeller University", "New York", "United States", "North America", "https://www.rockefeller.edu/"),
 "Conrad A. Nieduszynski": ("Earlham Institute", "Norwich", "United Kingdom", "Europe", "https://www.earlham.ac.uk/"),
 "Hasan Yardimci": ("The Francis Crick Institute", "London", "United Kingdom", "Europe", "https://www.crick.ac.uk/"),
 "Hiroyuki Araki": ("National Institute of Genetics", "Mishima", "Japan", "Asia", "https://www.nig.ac.jp/"),
 "Hideo Masai": ("Tokyo Metropolitan Institute of Medical Science", "Tokyo", "Japan", "Asia", "https://www.igakuken.or.jp/english/"),
 "Joseph T. P. Yeeles": ("MRC Laboratory of Molecular Biology", "Cambridge", "United Kingdom", "Europe", "https://www2.mrc-lmb.cam.ac.uk/group-leaders/t-to-z/joseph-yeeles/"),
 "Tom Deegan": ("Institute of Genetics and Cancer, University of Edinburgh", "Edinburgh", "United Kingdom", "Europe", "https://institute-genetics-cancer.ed.ac.uk/"),
 "Christoph F. Kurat": ("University of Bayreuth", "Bayreuth", "Germany", "Europe", "https://www.uni-bayreuth.de/"),
 "Niels Mailand": ("Novo Nordisk Foundation Center for Protein Research, University of Copenhagen", "Copenhagen", "Denmark", "Europe", "https://www.cpr.ku.dk/"),
 "Claus Storgaard Sørensen": ("University of Copenhagen", "Copenhagen", "Denmark", "Europe", "https://www.ku.dk/"),
 "Ian D. Hickson": ("University of Copenhagen", "Copenhagen", "Denmark", "Europe", "https://www.ku.dk/"),
 "Puck Knipscheer": ("Hubrecht Institute", "Utrecht", "Netherlands", "Europe", "https://www.hubrecht.eu/"),
 "Sarah A. E. Lambert": ("Institut Curie Research Center", "Orsay", "France", "Europe", "https://institut-curie.org/"),
 "Marco Foiani": ("IFOM, the FIRC Institute of Molecular Oncology", "Milan", "Italy", "Europe", "https://www.ifom.eu/"),
 "Marco Muzi-Falconi": ("University of Milan", "Milan", "Italy", "Europe", "https://www.unimi.it/"),
 "Andrés Aguilera": ("CABIMER, University of Seville", "Seville", "Spain", "Europe", "https://www.cabimer.es/"),
 "Angelos Constantinou": ("Institute of Human Genetics, CNRS / University of Montpellier", "Montpellier", "France", "Europe", "https://igh.cnrs.fr/"),
 "Wojciech Niedzwiedz": ("University of Oxford", "Oxford", "United Kingdom", "Europe", "https://www.ox.ac.uk/"),
 "Simon J. Boulton": ("The Francis Crick Institute", "London", "United Kingdom", "Europe", "https://www.crick.ac.uk/"),
 "Stephen C. West": ("The Francis Crick Institute", "London", "United Kingdom", "Europe", "https://www.crick.ac.uk/"),
 "Jessica A. Downs": ("The Institute of Cancer Research", "London", "United Kingdom", "Europe", "https://www.icr.ac.uk/"),
 "Steve P. Jackson": ("University of Cambridge", "Cambridge", "United Kingdom", "Europe", "https://www.cam.ac.uk/"),
 "Keith W. Caldecott": ("University of Sussex", "Brighton", "United Kingdom", "Europe", "https://www.sussex.ac.uk/"),
 "Fumiko Esashi": ("University of Oxford", "Oxford", "United Kingdom", "Europe", "https://www.ox.ac.uk/"),
 "Matthew C. Whitby": ("University of Oxford", "Oxford", "United Kingdom", "Europe", "https://www.ox.ac.uk/"),
 "Peter McGlynn": ("University of York", "York", "United Kingdom", "Europe", "https://www.york.ac.uk/"),
 "Heath Murray": ("Newcastle University", "Newcastle upon Tyne", "United Kingdom", "Europe", "https://www.ncl.ac.uk/"),
 "Stephan Uphoff": ("University of Oxford", "Oxford", "United Kingdom", "Europe", "https://www.ox.ac.uk/"),
 "David Rueda": ("Imperial College London", "London", "United Kingdom", "Europe", "https://www.imperial.ac.uk/"),
 "Stephen C. Kowalczykowski": ("University of California, Davis", "Davis", "United States", "North America", "https://www.ucdavis.edu/"),
 "Sue Jinks-Robertson": ("Duke University", "Durham", "United States", "North America", "https://www.duke.edu/"),
 "Lorraine S. Symington": ("Columbia University", "New York", "United States", "North America", "https://www.columbia.edu/"),
 "James E. Haber": ("Brandeis University", "Waltham", "United States", "North America", "https://www.brandeis.edu/"),
 "Richard D. Kolodner": ("Ludwig Institute / University of California San Diego", "La Jolla", "United States", "North America", "https://www.ucsd.edu/"),
 "Thomas D. Petes": ("Duke University", "Durham", "United States", "North America", "https://www.duke.edu/"),
 "Graham C. Walker": ("Massachusetts Institute of Technology", "Cambridge", "United States", "North America", "https://biology.mit.edu/"),
 "Susan T. Lovett": ("Brandeis University", "Waltham", "United States", "North America", "https://www.brandeis.edu/"),
 "Houra Merrikh": ("Vanderbilt University", "Nashville", "United States", "North America", "https://www.vanderbilt.edu/"),
 "Alessandro Vindigni": ("Washington University School of Medicine", "St Louis", "United States", "North America", "https://medicine.wustl.edu/"),
 "Maria Jasin": ("Memorial Sloan Kettering Cancer Center", "New York", "United States", "North America", "https://www.mskcc.org/"),
 "Titia de Lange": ("The Rockefeller University", "New York", "United States", "North America", "https://www.rockefeller.edu/"),
 "Agnel Sfeir": ("Memorial Sloan Kettering Cancer Center", "New York", "United States", "North America", "https://www.mskcc.org/"),
 "Roger A. Greenberg": ("University of Pennsylvania", "Philadelphia", "United States", "North America", "https://www.upenn.edu/"),
 "Alberto Ciccia": ("Columbia University", "New York", "United States", "North America", "https://www.columbia.edu/"),
 "Stephen J. Elledge": ("Harvard Medical School / HHMI", "Boston", "United States", "North America", "https://hms.harvard.edu/"),
 "Bik-Kwoon Tye": ("Hong Kong University of Science and Technology", "Hong Kong", "China", "Asia", "https://hkust.edu.hk/"),
 "Yuanliang Zhai": ("Hong Kong University of Science and Technology", "Hong Kong", "China", "Asia", "https://hkust.edu.hk/"),
 "Huilin Li": ("Van Andel Institute", "Grand Rapids", "United States", "North America", "https://www.vai.org/"),
 "Tatsuro S. Takahashi": ("Kyushu University", "Fukuoka", "Japan", "Asia", "https://www.kyushu-u.ac.jp/en/"),
 "Akira Shinohara": ("Osaka University", "Osaka", "Japan", "Asia", "https://www.osaka-u.ac.jp/en"),
 "Andrew J. Deans": ("St Vincent's Institute of Medical Research", "Melbourne", "Australia", "Oceania", "https://www.svi.edu.au/"),
 "Ian Grainge": ("University of Newcastle", "Newcastle", "Australia", "Oceania", "https://www.newcastle.edu.au/"),
 "Uttam Surana": ("Institute of Molecular and Cell Biology, A*STAR", "Singapore", "Singapore", "Asia", "https://www.a-star.edu.sg/imcb"),
 "Primo Schär": ("University of Basel", "Basel", "Switzerland", "Europe", "https://www.unibas.ch/"),
 "Thomas C. R. Miller": ("University of Copenhagen / The Francis Crick Institute", "Copenhagen", "Denmark", "Europe", "https://www.ku.dk/"),
}

LAB_URL_OVERRIDES = {
 "John F. X. Diffley": "https://www.crick.ac.uk/research/labs/john-diffley",
 "Stephen P. Bell": "https://bell-lab.mit.edu/",
 "Joseph T. P. Yeeles": "https://www2.mrc-lmb.cam.ac.uk/group-leaders/t-to-z/joseph-yeeles/",
 "Alessandro Costa": "https://www.crick.ac.uk/research/labs/alessandro-costa",
 "Simon J. Boulton": "https://www.crick.ac.uk/research/labs/simon-boulton",
 "Stephen C. West": "https://www.crick.ac.uk/research/labs/stephen-west",
}

TECHNIQUE_GROUPS = {
 "Biochemistry & reconstitution": ("biochemistry", "reconstitution"),
 "Structural biology & cryo-EM": ("cryo-em", "crystallography", "structural biology", "structural"),
 "Single-molecule & biophysics": ("single-molecule", "magnetic tweezers", "optical tweezers", "dna curtains", "microfluidics"),
 "Cell biology & imaging": ("cell biology", "imaging", "mouse model", "mouse genetics"),
 "Genomics & sequencing": ("genomics", "sequencing", "chromosome conformation"),
 "Genetics & genome engineering": ("yeast genetics", "bacterial genetics", "molecular genetics", "genetics", "genome engineering"),
 "Proteomics & mass spectrometry": ("proteomics", "phosphoproteomics", "mass spectrometry", "mass spec"),
 "Computational & systems biology": ("computational", "systems biology"),
 "DNA fiber & electron microscopy": ("dna fiber", "electron microscopy"),
 "Extracts & cell-free systems": ("xenopus", "extract", "cell-free"),
}

REPLICATION_GROUPS = {
 "Initiation & origin licensing": ("initiation", "origin", "licensing", "mcm loading", "ddk/cdc7"),
 "Replisome architecture & dynamics": ("replisome", "helicase", "sliding clamp", "replication dynamics", "mcm helicase"),
 "Replication stress & fork protection": ("replication stress", "fork protection", "checkpoint", "atr", "fork remodeling", "nascent dna"),
 "DNA repair & damage tolerance": ("dna repair", "homologous recombination", "crosslink", "brca", "sumo", "damage tolerance", "mismatch repair", "double-strand", "fanconi"),
 "Timing & genome organization": ("replication timing", "genome organization", "nuclear organization", "cell-cycle", "cell cycle"),
 "Chromatin inheritance & cohesion": ("chromatin", "histone", "cohesion", "epigenetic"),
 "Transcription conflicts & R-loops": ("transcription", "r-loop"),
 "Termination, restart & topology": ("termination", "restart", "topological", "topoisomerase", "fork repair", "replication repair"),
 "Polymerases, fidelity & mutagenesis": ("polymerase", "pcna", "okazaki", "fidelity", "mutagenesis", "translesion"),
 "Telomeres & difficult templates": ("telomere", "difficult-to-replicate", "chromosome ends", "replication barrier", "fork collision"),
}

def group_labels(details, mapping):
    text = details.lower()
    labels = [label for label, needles in mapping.items() if any(n in text for n in needles)]
    return labels or [next(iter(mapping))]

def get_json(url: str, cache_name: str):
    p = RAW / cache_name
    if p.exists():
        return json.loads(p.read_text())
    req = urllib.request.Request(url, headers={"User-Agent":"replication-survey/1.0 (academic data curation; mailto:research@example.org)"})
    last_error = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=90) as f:
                data = json.load(f)
            break
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    else:
        raise last_error
    p.write_text(json.dumps(data))
    time.sleep(0.12)
    return data

def norm(s): return re.sub(r"[^a-z]", "", (s or "").lower())

def resolve_author(name, expected):
    if name in MANUAL_AUTHOR_IDS:
        aid = MANUAL_AUTHOR_IDS[name]
        a = get_json(f"https://api.openalex.org/authors/{aid}", f"author_{aid}.json")
        return a, 20.0
    q = urllib.parse.quote(name)
    data = get_json(f"https://api.openalex.org/authors?search={q}&per-page=10", f"author_search_{norm(name)}.json")
    target = norm(name)
    best = None
    best_score = -1
    for a in data.get("results", []):
        dn = norm(a.get("display_name"))
        name_score = 8 if dn == target else (5 if dn in target or target in dn else 0)
        inst = " ".join(x.get("display_name", "") for x in (a.get("last_known_institutions") or []))
        inst_score = 6 if norm(expected) in norm(inst) else 0
        score = name_score + inst_score + math.log1p(a.get("cited_by_count", 0)) / 5
        if score > best_score:
            best_score, best = score, a
    return best, best_score

def fetch_works(author_id):
    aid = author_id.rsplit("/", 1)[-1]
    url = ("https://api.openalex.org/works?filter=author.id:" + aid +
           "&sort=cited_by_count:desc&per-page=200&select=id,doi,display_name,publication_year,publication_date,cited_by_count,authorships,topics,primary_location,type")
    return get_json(url, f"works_{aid}.json").get("results", [])

def fetch_recent_works(author_id):
    aid = author_id.rsplit("/", 1)[-1]
    url = ("https://api.openalex.org/works?filter=author.id:" + aid +
           f",from_publication_date:{RECENT_START},to_publication_date:{AS_OF}" +
           "&sort=cited_by_count:desc&per-page=200&select=id,doi,display_name,publication_year,publication_date,cited_by_count,authorships,topics,primary_location,type")
    return get_json(url, f"recent_works_{aid}_{AS_OF}.json").get("results", [])

def topic_text(w):
    return " ".join(t.get("display_name", "") for t in w.get("topics", []))

def relevant(w):
    return bool(RELEVANCE.search((w.get("display_name") or "") + " " + topic_text(w)))

def paper_string(w):
    title = (w.get("display_name") or "Untitled").replace(";", ",")
    yr = w.get("publication_year") or "n.d."
    cites = w.get("cited_by_count", 0)
    url = w.get("doi") or w.get("id") or ""
    return f"{title} ({yr}; OpenAlex citations={cites}; {url})"

def recent_paper_string(w):
    title = (w.get("display_name") or "Untitled").replace(";", ",")
    when = w.get("publication_date") or str(w.get("publication_year") or "n.d.")
    cites = w.get("cited_by_count", 0)
    url = w.get("doi") or w.get("id") or ""
    return f"{title} ({when}; OpenAlex citations={cites}; {url})"

def percentile(vals, x):
    if len(set(vals)) <= 1: return 50.0
    return 100.0 * sum(v <= x for v in vals) / len(vals)

def main():
    records = []
    works_by_id = {}
    author_name_to_roster = {}
    resolution = []
    for idx, (name, expected, stage, techniques, subfields, eligible) in enumerate(ROSTER, 1):
        author, score = resolve_author(name, expected)
        if not author:
            resolution.append({"person":name,"status":"UNRESOLVED"})
            continue
        aid = author["id"].rsplit("/", 1)[-1]
        works = fetch_works(author["id"])
        recent_works = fetch_recent_works(author["id"])
        rel = [w for w in works if relevant(w)]
        recent = [w for w in recent_works if relevant(w)]
        # Do not backfill ranking evidence with unrelated publications. Sparse
        # profiles remain sparse and are exposed in the audit/caveat fields.
        rel.sort(key=lambda w:w.get("cited_by_count",0), reverse=True)
        recent.sort(key=lambda w:w.get("cited_by_count",0), reverse=True)

        insts = author.get("last_known_institutions") or []
        inst = insts[0] if insts else {}
        if inst.get("id"):
            iid = inst["id"].rsplit("/",1)[-1]
            inst_full = get_json(f"https://api.openalex.org/institutions/{iid}", f"institution_{iid}.json")
        else: inst_full = {}
        geo = inst_full.get("geo") or {}
        cc = inst_full.get("country_code") or inst.get("country_code") or ""
        curated_aff = CURATED_AFFILIATIONS.get(name)

        # Recent collaborator counts, paper metadata, and inferred first-author candidates.
        collab = Counter(); collab_papers = defaultdict(list); trainee = Counter(); trainee_papers = defaultdict(list)
        for w in recent:
            target_authorship = next((au for au in w.get("authorships", []) if (((au.get("author") or {}).get("id") or "").rsplit("/",1)[-1] == aid)), {})
            target_is_senior = target_authorship.get("author_position") == "last" or target_authorship.get("is_corresponding") is True
            for au in w.get("authorships", []):
                auid = ((au.get("author") or {}).get("id") or "").rsplit("/",1)[-1]
                auname = (au.get("author") or {}).get("display_name") or ""
                if auid and auid != aid:
                    collab[auname] += 1
                    collab_papers[auname].append(f"{w.get('publication_year')}:{w.get('display_name')}")
                if target_is_senior and au.get("author_position") == "first" and auid != aid:
                    trainee[auname] += 1 + math.log1p(w.get("cited_by_count",0))
                    trainee_papers[auname].append(w.get("display_name") or "")
        collabs = []
        for n, count in collab.most_common(5):
            meta = " | ".join(collab_papers[n][:2]).replace(";", ",")
            collabs.append(f"{n} (shared recent papers={count}; examples={meta})")
        trainees = []
        for n, val in trainee.most_common(5):
            ex = " | ".join(trainee_papers[n][:2]).replace(";", ",")
            trainees.append(f"{n} (inferred first-author candidate; examples={ex})")

        # Infer "from the lab" by prioritizing the focal researcher as last or
        # corresponding author. Backfill from other authored records only when
        # fewer than five senior-author papers are indexed.
        recent_by_date = sorted(recent_works, key=lambda w:(w.get("publication_date") or "", w.get("cited_by_count",0)), reverse=True)
        senior_recent, other_recent = [], []
        for w in recent_by_date:
            target = next((au for au in w.get("authorships", []) if (((au.get("author") or {}).get("id") or "").rsplit("/",1)[-1] == aid)), {})
            (senior_recent if target.get("author_position") == "last" or target.get("is_corresponding") is True else other_recent).append(w)
        senior_ids = {w.get("id") for w in senior_recent}
        newest_lab_works = (senior_recent + [w for w in other_recent if w.get("id") not in senior_ids])[:5]
        technique_groups = group_labels(techniques, TECHNIQUE_GROUPS)
        replication_groups = group_labels(subfields, REPLICATION_GROUPS)
        scholar_search = "https://scholar.google.com/citations?view_op=search_authors&hl=en&mauthors=" + urllib.parse.quote(name)
        lab_url = LAB_URL_OVERRIDES.get(name) or (curated_aff[4] if curated_aff else (inst.get("ror") or inst.get("id") or ""))

        rec = {
            "rank":"", "ranking_status":"ranked" if eligible else "additional/unranked",
            "person":name, "openalex_display_name":author.get("display_name",""),
            "career_impact_category":stage,
            "affiliation":curated_aff[0] if curated_aff else (inst.get("display_name") or expected),
            "city":curated_aff[1] if curated_aff else (geo.get("city") or ""),
            "country":curated_aff[2] if curated_aff else COUNTRY_NAMES.get(cc, cc),
            "continent":curated_aff[3] if curated_aff else CONTINENT.get(cc, "Other/unknown"),
            "top_5_collaborators_2021_2026":" || ".join(collabs),
            "top_5_papers_all_time":" || ".join(paper_string(w) for w in rel[:5]),
            "top_5_papers_2021_2026":" || ".join(paper_string(w) for w in recent[:5]),
            "five_most_recent_lab_papers":" || ".join(recent_paper_string(w) for w in newest_lab_works),
            "recent_lab_paper_evidence":"all indexed works ordered newest-first; prioritizes records where focal researcher is last and/or corresponding author, then backfills from other authored works when fewer than five senior-author records are indexed; verify laboratory provenance for backfilled items",
            "technique_expertise":"; ".join(technique_groups),
            "replication_expertise_subfield":"; ".join(replication_groups),
            "technique_details":techniques,
            "replication_expertise_details":subfields,
            "top_5_trainees_or_future_leaders":" || ".join(trainees),
            "trainee_evidence_type":"algorithmic candidates: first authors on recent field-relevant papers where the focal researcher is last and/or corresponding author; mentorship/training relationship not independently verified",
            "openalex_author_id":aid, "orcid":author.get("orcid") or "",
            "author_source_url":author.get("id") or "",
            "affiliation_source_url":curated_aff[4] if curated_aff else (inst.get("ror") or inst.get("id") or ""),
            "lab_website_url":lab_url,
            "lab_website_link_type":"specific lab/group page" if name in LAB_URL_OVERRIDES else "official institution or research-centre page; specific lab page not independently verified",
            "google_scholar_url":scholar_search,
            "google_scholar_link_type":"Google Scholar author search; exact public profile not independently verified",
            "works_source_url":f"https://api.openalex.org/works?filter=author.id:{aid}",
            "source_notes":f"OpenAlex snapshot accessed {AS_OF}; affiliation {'manually corrected after OpenAlex identity audit' if curated_aff else 'uses OpenAlex last-known institution'} and should be rechecked before outreach; citations are dynamic",
            "lifetime_relevant_works":len(rel), "lifetime_relevant_citations":sum(w.get("cited_by_count",0) for w in rel),
            "recent_relevant_works":len(recent), "recent_relevant_citations":sum(w.get("cited_by_count",0) for w in recent),
            "recent_distinct_collaborators":len(collab), "resolution_confidence_score":round(score,2),
        }
        records.append(rec)
        works_by_id[aid] = recent
        author_name_to_roster[norm(author.get("display_name"))] = name
        author_name_to_roster[norm(name)] = name
        for alias in ALIASES.get(name, []): author_name_to_roster[norm(alias)] = name
        resolution.append({"person":name,"matched":author.get("display_name"),"openalex_id":aid,"expected_institution":expected,"matched_institutions":"; ".join(x.get("display_name","") for x in insts),"confidence_score":round(score,2)})

    ranked = [r for r in records if r["ranking_status"] == "ranked"]
    # Percentile-based score resists citation outliers and remains transparent.
    lc = [r["lifetime_relevant_citations"] for r in ranked]
    lw = [r["lifetime_relevant_works"] for r in ranked]
    rc = [r["recent_relevant_citations"] for r in ranked]
    rw = [r["recent_relevant_works"] for r in ranked]
    cd = [r["recent_distinct_collaborators"] for r in ranked]
    for r in ranked:
        life = .75*percentile(lc,r["lifetime_relevant_citations"]) + .25*percentile(lw,r["lifetime_relevant_works"])
        recent = .65*percentile(rc,r["recent_relevant_citations"]) + .25*percentile(rw,r["recent_relevant_works"]) + .10*percentile(cd,r["recent_distinct_collaborators"])
        r["lifetime_impact_score_0_100"] = round(life,1)
        r["impact_2021_2026_score_0_100"] = round(recent,1)
        r["combined_impact_score_0_100"] = round(.55*life + .45*recent,1)
    for r in records:
        if r["ranking_status"] != "ranked":
            r["lifetime_impact_score_0_100"] = ""; r["impact_2021_2026_score_0_100"] = ""; r["combined_impact_score_0_100"] = ""
    ranked.sort(key=lambda r:r["combined_impact_score_0_100"], reverse=True)
    for i,r in enumerate(ranked,1): r["rank"] = i
    extras = [r for r in records if r["ranking_status"] != "ranked"]
    records = ranked + extras

    fields = [
        "rank","ranking_status","person","openalex_display_name","career_impact_category","combined_impact_score_0_100","lifetime_impact_score_0_100","impact_2021_2026_score_0_100",
        "affiliation","city","country","continent","top_5_collaborators_2021_2026","top_5_papers_all_time","top_5_papers_2021_2026","five_most_recent_lab_papers","recent_lab_paper_evidence","technique_expertise","replication_expertise_subfield","technique_details","replication_expertise_details","top_5_trainees_or_future_leaders","trainee_evidence_type",
        "lifetime_relevant_works","lifetime_relevant_citations","recent_relevant_works","recent_relevant_citations","recent_distinct_collaborators","openalex_author_id","orcid","author_source_url","affiliation_source_url","lab_website_url","lab_website_link_type","google_scholar_url","google_scholar_link_type","works_source_url","source_notes","resolution_confidence_score"
    ]
    with (OUT/"dna_replication_researchers.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(records)
    with (OUT/"author_resolution_audit.csv").open("w",newline="",encoding="utf-8") as f:
        keys=sorted(set().union(*(x.keys() for x in resolution))); w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(resolution)

    # Researcher nodes and recent coauthorship edges among roster members.
    nodes=[]
    for r in records:
        nodes.append({k:r[k] for k in ["person","rank","ranking_status","career_impact_category","combined_impact_score_0_100","affiliation","city","country","continent","technique_expertise","replication_expertise_subfield","technique_details","replication_expertise_details","lab_website_url","google_scholar_url","openalex_author_id","author_source_url"]})
    by_aid={r["openalex_author_id"]:r for r in records}
    edge_papers=defaultdict(dict)
    for aid,r in by_aid.items():
        for w in works_by_id.get(aid,[]):
            roster_aids=[]
            for au in w.get("authorships",[]):
                x=((au.get("author") or {}).get("id") or "").rsplit("/",1)[-1]
                if x in by_aid: roster_aids.append(x)
            for i,a in enumerate(sorted(set(roster_aids))):
                for b in sorted(set(roster_aids))[i+1:]:
                    edge_papers[(a,b)][w.get("id")]=w
    edges=[]
    for (a,b), papers in edge_papers.items():
        ps=sorted(papers.values(),key=lambda w:(w.get("publication_year") or 0,w.get("cited_by_count",0)),reverse=True)
        edges.append({"source":by_aid[a]["person"],"target":by_aid[b]["person"],"weight_recent_shared_papers":len(ps),"shared_citation_sum":sum(w.get("cited_by_count",0) for w in ps),"supporting_papers":" || ".join(paper_string(w) for w in ps),"years":";".join(str(w.get("publication_year")) for w in ps),"evidence_source":"OpenAlex coauthorship metadata"})
    edges.sort(key=lambda e:(e["weight_recent_shared_papers"],e["shared_citation_sum"]),reverse=True)
    with (OUT/"replication_network_nodes.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=nodes[0].keys()); w.writeheader(); w.writerows(nodes)
    with (OUT/"replication_network_edges.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=edges[0].keys() if edges else ["source","target","weight_recent_shared_papers"]); w.writeheader(); w.writerows(edges)
    (OUT/"replication_community_network.json").write_text(json.dumps({"metadata":{"as_of":AS_OF,"edge_window":f"2021-01-01 through {AS_OF}","node_count":len(nodes),"edge_count":len(edges)},"nodes":[{"id":n["person"],**n} for n in nodes],"edges":edges},indent=2,ensure_ascii=False))

    # Dependency-free GraphML export.
    import xml.etree.ElementTree as ET
    ns="http://graphml.graphdrawing.org/xmlns"; ET.register_namespace("",ns)
    root=ET.Element(f"{{{ns}}}graphml")
    node_keys=list(nodes[0].keys()); edge_keys=list(edges[0].keys()) if edges else []
    for i,k in enumerate(node_keys):
        typ = "double" if k == "combined_impact_score_0_100" else "string"
        ET.SubElement(root,f"{{{ns}}}key",id=f"n{i}",attrib={"for":"node","attr.name":k,"attr.type":typ})
    for i,k in enumerate(edge_keys):
        typ = "long" if k in {"weight_recent_shared_papers","shared_citation_sum"} else "string"
        ET.SubElement(root,f"{{{ns}}}key",id=f"e{i}",attrib={"for":"edge","attr.name":k,"attr.type":typ})
    graph=ET.SubElement(root,f"{{{ns}}}graph",id="DNA_replication_community",edgedefault="undirected")
    for n in nodes:
        el=ET.SubElement(graph,f"{{{ns}}}node",id=n["person"])
        for i,k in enumerate(node_keys): ET.SubElement(el,f"{{{ns}}}data",key=f"n{i}").text=str(n.get(k,""))
    for j,e in enumerate(edges):
        el=ET.SubElement(graph,f"{{{ns}}}edge",id=f"edge{j+1}",source=e["source"],target=e["target"])
        for i,k in enumerate(edge_keys): ET.SubElement(el,f"{{{ns}}}data",key=f"e{i}").text=str(e.get(k,""))
    ET.ElementTree(root).write(OUT/"replication_community_network.graphml",encoding="utf-8",xml_declaration=True)
    print(json.dumps({"records":len(records),"ranked":len(ranked),"additional":len(extras),"edges":len(edges)},indent=2))

if __name__ == "__main__": main()
