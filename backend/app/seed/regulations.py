"""Baseline statutory library (plain-language summaries of key provisions).

These summaries seed the regulation register and the RAG knowledge base. They
are paraphrased for operational guidance; the authoritative text is the
official Gazette publication of each Act/Regulation, which administrators can
upload through Documents (OCR → embeddings) to extend the knowledge base.
"""

from __future__ import annotations

from app.models.enums import ComplianceCategory as C

REGULATIONS: list[dict] = [
    # ------------------------------------------------------------- safety
    {"code": "MA1952-S17", "act": "Mines Act, 1952", "section": "Section 17", "category": C.SAFETY,
     "authority": "DGMS", "title": "Appointment of mine manager",
     "text": "Every mine must be under a single manager holding the prescribed qualifications, appointed by the "
             "owner or agent. The manager is responsible for the overall control, management and direction of the "
             "mine, and the appointment (and any change) must be notified to the Chief Inspector of Mines. No mine "
             "may be worked without a duly appointed manager."},
    {"code": "MA1952-S22", "act": "Mines Act, 1952", "section": "Section 22", "category": C.SAFETY,
     "authority": "DGMS", "title": "Powers of Inspectors when causes of danger are not expressly provided against",
     "text": "Where an Inspector finds any matter, thing or practice in a mine that is dangerous to human life or "
             "safety, or defective, the Inspector may by written notice require the owner, agent or manager to "
             "remedy it within a specified period, and may prohibit employment of persons in the affected part of "
             "the mine until the danger is removed (prohibitory orders under Section 22(3))."},
    {"code": "MA1952-S23", "act": "Mines Act, 1952", "section": "Section 23", "category": C.SAFETY,
     "authority": "DGMS", "title": "Notice of accidents",
     "text": "Accidents causing loss of life or serious bodily injury, and dangerous occurrences such as explosions, "
             "ignitions, fires, inrush of water or roof/side falls, must be reported to the Chief Inspector, the "
             "Inspector and other prescribed authorities immediately and in the prescribed form. The site of a fatal "
             "accident must not be disturbed until inspected, except to rescue persons or prevent further danger."},
    {"code": "MA1952-S40", "act": "Mines Act, 1952", "section": "Section 40", "category": C.LABOUR,
     "authority": "DGMS", "title": "Employment of persons below eighteen years of age",
     "text": "No person below eighteen years of age shall be allowed to work in any mine or part thereof. "
             "Apprentices and trainees of at least sixteen years may be permitted to work under proper supervision "
             "as provided in the rules."},
    {"code": "MA1952-S48", "act": "Mines Act, 1952", "section": "Section 48", "category": C.LABOUR,
     "authority": "DGMS", "title": "Registers of persons employed",
     "text": "The owner, agent or manager must maintain registers of all persons employed, showing name, nature of "
             "employment, and the hours/relay of work, including persons employed by contractors, and must keep "
             "attendance records available for inspection. Attendance in underground workings must be recorded "
             "at the time of entry and exit."},
    {"code": "CMR2017-R32", "act": "Coal Mines Regulations, 2017", "section": "Regulation 32",
     "category": C.SAFETY, "authority": "DGMS", "title": "Management plans and principal hazard management",
     "text": "The owner shall identify principal hazards of the mine (such as roof and side falls, inundation, fire, "
             "gas and dust explosion, heavy machinery accidents) through a risk assessment and prepare a Safety "
             "Management Plan with principal hazard management plans, control measures, monitoring and review. "
             "The plan must be reviewed periodically and after any serious accident or change in conditions."},
    {"code": "CMR2017-R107", "act": "Coal Mines Regulations, 2017", "section": "Regulation 107",
     "category": C.SAFETY, "authority": "DGMS", "title": "Systematic support rules for roof and sides",
     "text": "In underground workings the manager must frame systematic support rules specifying the type, spacing "
             "and method of setting supports for roof and sides based on scientific study of strata. No person shall "
             "work or pass under unsupported roof. Supports must be installed promptly after each cycle of "
             "extraction and regularly examined; any support found defective must be replaced forthwith."},
    {"code": "CMR2017-R145", "act": "Coal Mines Regulations, 2017", "section": "Regulation 145",
     "category": C.SAFETY, "authority": "DGMS", "title": "Ventilation standards",
     "text": "Every underground working must be ventilated so that the air contains not less than 19 percent oxygen "
             "and not more than 0.5 percent carbon dioxide, and the percentage of inflammable gas in the general "
             "body of air does not exceed prescribed limits (0.75 percent in return airways of degree-II/III gassy "
             "seams, with withdrawal of persons at 1.25 percent). Air velocity and quantity must meet prescribed "
             "minimums at each working face and be measured and recorded at stated intervals."},
    {"code": "CMR2017-R164", "act": "Coal Mines Regulations, 2017", "section": "Regulation 164",
     "category": C.SAFETY, "authority": "DGMS", "title": "Precautions against inundation",
     "text": "Where workings approach any disused working, water-logged area, river, tank or other surface water "
             "body, precautions including advance boreholes, barriers of prescribed thickness, danger-zone plans and "
             "monsoon preparedness measures must be taken. Before each monsoon, embankments and drainage must be "
             "inspected and a report submitted; emergency pumping capacity must be ensured."},
    {"code": "CMR2017-R170", "act": "Coal Mines Regulations, 2017", "section": "Regulation 170",
     "category": C.SAFETY, "authority": "DGMS", "title": "Precautions against fires and spontaneous heating",
     "text": "The owner must take measures to prevent, detect and control fires and spontaneous heating, including "
             "monitoring of carbon monoxide and temperature, sealing of abandoned areas, fire-fighting "
             "arrangements, and maintenance of fire-fighting equipment at specified places. Any sign of heating "
             "must be reported to the manager immediately and recorded."},
    {"code": "CMR2017-R196", "act": "Coal Mines Regulations, 2017", "section": "Regulation 196",
     "category": C.SAFETY, "authority": "DGMS", "title": "Transport rules and traffic management in opencast mines",
     "text": "The manager of every opencast mine using heavy earth moving machinery (dumpers, trucks, shovels) must "
             "frame traffic rules covering haul road width (at least three times the widest vehicle for two-way "
             "traffic), gradient, berms/parapets of at least half the wheel height, speed limits, right of way, "
             "lighting and segregation of light and heavy vehicles. Vehicles must have functional brakes, audiovisual "
             "reversing alarms and proximity warning devices, and be examined before each shift."},
    {"code": "CMR2017-R106", "act": "Coal Mines Regulations, 2017", "section": "Regulation 106",
     "category": C.SAFETY, "authority": "DGMS", "title": "Benches and slope stability in opencast workings",
     "text": "In opencast workings the height and width of benches and the overall slope must be designed on the "
             "basis of a scientific slope-stability study. In alluvium or soil, bench height must not exceed 3 m "
             "unless mechanised; overhangs and undercuts are prohibited. Slopes must be monitored, and cracks or "
             "signs of failure must lead to withdrawal of persons and remedial action."},
    {"code": "CMR2017-R191", "act": "Coal Mines Regulations, 2017", "section": "Regulation 191",
     "category": C.SAFETY, "authority": "DGMS", "title": "Personal protective equipment",
     "text": "Every person in a mine must wear the protective footwear and helmet provided by the owner; other PPE "
             "such as self-rescuers (underground), eye protection, ear protection in high-noise areas, dust masks "
             "and reflective jackets must be provided and used as required by the risk assessment. The owner must "
             "maintain a record of issue and replacement of PPE."},
    {"code": "MVTR1966-R8", "act": "Mines Vocational Training Rules, 1966", "section": "Rule 8",
     "category": C.LABOUR, "authority": "DGMS", "title": "Basic and refresher training",
     "text": "No person shall be employed in a mine unless they have completed basic training at a vocational "
             "training centre. Refresher training must be given at intervals not exceeding five years, and special "
             "training is required before a person is assigned to specified hazardous jobs. Training records must "
             "be maintained for each worker, including contractor workers."},
    {"code": "MR1955-R29B", "act": "Mines Rules, 1955", "section": "Rule 29B",
     "category": C.LABOUR, "authority": "DGMS", "title": "Initial and periodical medical examination",
     "text": "Every person employed in a mine must undergo an initial medical examination before employment and "
             "periodical medical examinations at intervals not exceeding five years, including tests for "
             "pneumoconiosis and noise-induced hearing loss. Persons found unfit must not be employed in the work "
             "concerned and records must be kept in the prescribed form."},
    # -------------------------------------------------------- environment
    {"code": "EPA1986-S15", "act": "Environment (Protection) Act, 1986", "section": "Section 15",
     "category": C.ENVIRONMENT, "authority": "MoEFCC / SPCB", "title": "Penalty for contravention of environmental standards",
     "text": "Failure to comply with the Act, rules, orders or directions (including emission and effluent "
             "standards and conditions of Environmental Clearance) is punishable with imprisonment and fine, with "
             "additional daily fines for continuing contravention. Mines must comply with coal-mine-specific "
             "standards notified under Schedule I of the Environment (Protection) Rules."},
    {"code": "EC-COND-HALFYEARLY", "act": "EIA Notification, 2006", "section": "Condition compliance",
     "category": C.ENVIRONMENT, "authority": "MoEFCC Regional Office",
     "title": "Half-yearly Environmental Clearance compliance report",
     "text": "Projects holding Environmental Clearance must submit half-yearly compliance reports on the stipulated "
             "EC conditions (by 1 June and 1 December) to the Regional Office of MoEFCC, the State Pollution Control "
             "Board and upload them on the project website, covering air and water quality monitoring, "
             "plantation, overburden management, and mine closure progress."},
    {"code": "AIRACT1981-S21", "act": "Air (Prevention and Control of Pollution) Act, 1981", "section": "Section 21",
     "category": C.ENVIRONMENT, "authority": "SPCB", "title": "Consent to operate — air",
     "text": "No industrial plant in an air pollution control area may be operated without the consent of the State "
             "Pollution Control Board. Coal mines must renew Consent to Operate before expiry, comply with ambient "
             "air quality norms for PM10 and PM2.5 at the mine boundary, and operate dust suppression measures such "
             "as water sprinklers, fog cannons and covered conveyance."},
    {"code": "WATERACT1974-S25", "act": "Water (Prevention and Control of Pollution) Act, 1974", "section": "Section 25",
     "category": C.ENVIRONMENT, "authority": "SPCB", "title": "Consent to discharge — mine water and effluents",
     "text": "No new outlet or discharge of sewage or trade effluent (including mine water) into a stream, well or on "
             "land may be made without SPCB consent. Mine water must be treated to meet discharge standards for "
             "pH, total suspended solids and oil & grease, and monitored at the prescribed frequency with records "
             "maintained."},
    {"code": "MCG-CLOSURE", "act": "Mine Closure Guidelines (Ministry of Coal)", "section": "Progressive closure",
     "category": C.ENVIRONMENT, "authority": "Ministry of Coal", "title": "Progressive and final mine closure plan",
     "text": "Every coal mine must implement an approved mine closure plan with progressive closure activities "
             "(backfilling, reclamation, afforestation of overburden dumps) and maintain an escrow account for "
             "final closure. Progress must be reported annually and audited every five years."},
    # ------------------------------------------------------------ production
    {"code": "CMR2017-R58", "act": "Coal Mines Regulations, 2017", "section": "Regulation 58",
     "category": C.PRODUCTION, "authority": "DGMS", "title": "Mine plans and sections",
     "text": "The owner must maintain accurate, up-to-date plans and sections of the mine prepared by a qualified "
             "surveyor, updated at prescribed intervals (surface and underground workings, danger zones, "
             "water-logged areas), and submit copies to the Chief Inspector as required."},
    {"code": "MCDR-RETURNS", "act": "Colliery Control Order / Ministry of Coal returns", "section": "Monthly returns",
     "category": C.PRODUCTION, "authority": "Coal Controller Organisation",
     "title": "Monthly production and despatch returns",
     "text": "Coal companies must submit monthly returns of coal production, despatch, stock and grade to the Coal "
             "Controller Organisation within the prescribed time, and annual returns in the prescribed format. "
             "Discrepancies between production, despatch and stock must be reconciled and explained."},
    {"code": "MA1952-ANNUAL-RETURN", "act": "Mines Rules, 1955", "section": "Annual return (Form B)",
     "category": C.PRODUCTION, "authority": "DGMS", "title": "Annual return to the Chief Inspector",
     "text": "The owner, agent or manager must submit an annual return to the Chief Inspector of Mines by 20 January "
             "each year giving particulars of employment, output, accidents and other prescribed information for "
             "the preceding calendar year."},
    # --------------------------------------------------------------- labour
    {"code": "CLRA1970-S12", "act": "Contract Labour (Regulation and Abolition) Act, 1970", "section": "Section 12",
     "category": C.LABOUR, "authority": "Chief Labour Commissioner (Central)", "title": "Licensing of contractors",
     "text": "No contractor to whom the Act applies may undertake work through contract labour except under a licence "
             "issued by the licensing officer. The principal employer must be registered and must ensure contractors "
             "hold valid licences, pay wages in the presence of the principal employer's representative, and "
             "provide canteens, rest rooms, drinking water and first aid."},
    {"code": "CLRA1970-S21", "act": "Contract Labour (Regulation and Abolition) Act, 1970", "section": "Section 21",
     "category": C.LABOUR, "authority": "Chief Labour Commissioner (Central)", "title": "Responsibility for payment of wages",
     "text": "The contractor is responsible for payment of wages before the expiry of the prescribed wage period. "
             "If the contractor fails to pay, the principal employer is liable to pay the full wages and may recover "
             "the amount from the contractor. Wages for contract workers in coal mines must be at least the rates "
             "notified (including HPC-recommended wages for CIL contract workers)."},
    {"code": "OSH2020-S6", "act": "Occupational Safety, Health and Working Conditions Code, 2020", "section": "Section 6",
     "category": C.LABOUR, "authority": "Ministry of Labour & Employment", "title": "Duties of employer",
     "text": "Every employer must ensure a workplace free from hazards, provide free annual health examinations for "
             "prescribed classes of employees, issue appointment letters, and ensure safety and health standards "
             "are maintained, including for contract workers engaged through contractors."},
    {"code": "CMPF-REMIT", "act": "Coal Mines Provident Fund and Miscellaneous Provisions Act, 1948",
     "section": "Contributions", "category": C.LABOUR, "authority": "CMPFO",
     "title": "Remittance of provident fund and pension contributions",
     "text": "Employers in coal mines must deduct and remit provident fund and pension contributions for all "
             "eligible employees, including contract workers, to the Coal Mines Provident Fund Organisation within "
             "the due date each month, and file the prescribed returns. Delays attract damages and interest."},
]
