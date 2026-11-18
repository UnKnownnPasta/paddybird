const fs=require('fs');
const D=require('docx');
const {Document,Packer,Paragraph,TextRun,ImageRun,AlignmentType,HeadingLevel,Table,TableRow,TableCell,WidthType,BorderStyle,ShadingType,Footer,PageNumber,TableOfContents,LevelFormat,PageBreak,TabStopType}=D;
const F="Times New Roman", RED="C00000";
// inline markup: **bold**, *italic*
function runs(t,o={}){
  const out=[];const re=/(\*\*[^*]+\*\*|\*[^*]+\*)/g;let last=0,m;
  const base={font:F,size:o.size||24,color:o.color,bold:o.bold,italics:o.italics};
  while((m=re.exec(t))){ if(m.index>last) out.push(new TextRun({...base,text:t.slice(last,m.index)}));
    const s=m[0]; if(s.startsWith('**')) out.push(new TextRun({...base,text:s.slice(2,-2),bold:true})); else out.push(new TextRun({...base,text:s.slice(1,-1),italics:true}));
    last=m.index+s.length;}
  if(last<t.length) out.push(new TextRun({...base,text:t.slice(last)}));
  return out;
}
const P=(t,o={})=>new Paragraph({alignment:o.align||AlignmentType.JUSTIFIED,spacing:{line:360,after:o.after??120,before:o.before||0},keepNext:o.keepNext,indent:o.indent,children:runs(t,o)});
const H1=t=>new Paragraph({heading:HeadingLevel.HEADING_1,pageBreakBefore:!t.startsWith("1."),children:[new TextRun({text:t,font:F})]});
const H2=t=>new Paragraph({heading:HeadingLevel.HEADING_2,children:[new TextRun({text:t,font:F})]});
const H3=t=>new Paragraph({heading:HeadingLevel.HEADING_3,children:[new TextRun({text:t,font:F})]});
const B=t=>new Paragraph({numbering:{reference:"bul",level:0},alignment:AlignmentType.JUSTIFIED,spacing:{line:360,after:60},children:runs(t)});
const N=(t,ref="num")=>new Paragraph({numbering:{reference:ref,level:0},alignment:AlignmentType.JUSTIFIED,spacing:{line:360,after:60},children:runs(t)});
const CAP=t=>new Paragraph({alignment:AlignmentType.CENTER,keepNext:t.startsWith("Table"),spacing:{before:60,after:200},children:runs(t,{size:22,italics:true})});
const bd={style:BorderStyle.SINGLE,size:4,color:"000000"};
const borders={top:bd,bottom:bd,left:bd,right:bd};
function table(widths,rows,{header=true,align=[]}={}){
  const total=widths.reduce((a,b)=>a+b,0);
  return new Table({width:{size:total,type:WidthType.DXA},columnWidths:widths,
    rows:rows.map((r,ri)=>new TableRow({tableHeader:header&&ri===0,cantSplit:true,children:r.map((c,ci)=>new TableCell({
      width:{size:widths[ci],type:WidthType.DXA},borders,
      shading:header&&ri===0?{fill:"E7E6E6",type:ShadingType.CLEAR,color:"auto"}:undefined,
      margins:{top:60,bottom:60,left:100,right:100},
      children:[new Paragraph({alignment:(header&&ri===0)?AlignmentType.CENTER:(align[ci]||AlignmentType.LEFT),spacing:{line:264,after:0},keepNext:ri<rows.length-1,
        children:runs(c,{size:22,bold:header&&ri===0})})]}))}))});
}
const gap=()=>new Paragraph({spacing:{after:120},children:[]});
const img=(f,w,h)=>new ImageRun({type:"png",data:fs.readFileSync(f),transformation:{width:w,height:h}});


const rule={style:BorderStyle.SINGLE,size:12,color:"000000",space:1};
function mkHeader(){return new D.Header({children:[new Paragraph({border:{bottom:rule},spacing:{after:0},children:[new TextRun({text:"",font:F,size:20})]})]});}
function mkFooter(){return new Footer({children:[new Paragraph({border:{top:rule},tabStops:[{type:TabStopType.RIGHT,position:8651}],spacing:{before:0},children:[new TextRun({text:"Dept. of CSE, RVITM",font:F,size:20}),new TextRun({children:["\t",PageNumber.CURRENT],font:F,size:20})]})]});}
// ---------------- cover ----------------
const C=(t,o={})=>new Paragraph({alignment:AlignmentType.CENTER,spacing:{before:o.before||0,after:o.after??0,line:o.line},children:[new TextRun({text:t,font:F,size:o.size||24,bold:o.bold,italics:o.italics,color:o.color})]});
const team=["Nikhil S Rao (1RF24CS112)","Sai Bhuwan S (1RF24CS136)","Yashita Murlidhar Mandavilli (1RF24CS183)","Shashwat Mittal (1RF24CS145)"];
const cover=[
  C("VISVESVARAYA TECHNOLOGICAL UNIVERSITY",{size:28,bold:true,color:RED}),
  C("\u201CJnana Sangama\u201D, Belagavi, Karnataka",{size:26,bold:true,color:RED,after:160}),
  new Paragraph({alignment:AlignmentType.CENTER,spacing:{after:300},children:[img("cimg-000.png",64,91)]}),
  C("A Mini Project on",{size:24,bold:true,after:140}),
  C("\u201CPaddybird: Estimating Flooded Paddy Area from Satellite Maps and a Small Field Sample\u201D",{size:32,bold:true,italics:true,after:300}),
  C("Submitted in partial fulfillment for Partial Mini Project Report",{size:22,italics:true,after:20}),
  C("In",{size:22,italics:true,after:20}),
  C("\u201CMini Project (BCS586)\u201D",{size:20,after:20}),
  C("V Semester, Academic Year 2026 \u2013 2027 (Odd)",{size:20,after:20}),
  C("of",{size:22,italics:true,after:80}),
  C("BACHELOR OF ENGINEERING",{size:24,bold:true,color:RED,after:20}),
  C("In",{size:24,bold:true,italics:true,color:RED,after:20}),
  C("COMPUTER SCIENCE AND ENGINEERING",{size:24,bold:true,color:RED,after:300}),
  C("Submitted by",{size:22,before:200,bold:true,italics:true,color:RED,after:120}),
  ...team.map(t=>C(t,{size:22,bold:true,after:60})),
  C("Under the guidance of",{size:22,bold:true,italics:true,color:RED,before:260,after:100}),
  C("Mr. S Murugan",{size:22,bold:true,after:20}),
  C("Assistant Professor, Dept. of CSE, RVITM",{size:20,bold:true,after:200}),
  C("November 2026",{size:22,bold:true,after:0}),
  new Paragraph({alignment:AlignmentType.CENTER,spacing:{before:700,after:100},children:[img("cimg-001.png",62,76)]}),
  new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({text:"RV INSTITUTE OF TECHNOLOGY AND MANAGEMENT",font:F,size:24,bold:true,color:RED}),new TextRun({text:"\u00AE",font:F,size:24,bold:true,color:RED,superScript:true})]}),
  new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({text:"(Affiliated to Visvesvaraya Technological University, Belagavi & Approved by AICTE, New Delhi)",font:F,size:14,bold:true})]}),
  new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({text:"Chaitanya Layout, JP Nagar 8",font:F,size:14,bold:true}),new TextRun({text:"th",font:F,size:14,bold:true,superScript:true}),new TextRun({text:" Phase, Kothanur, Bengaluru-560076",font:F,size:14,bold:true})]}),
];

// ---------------- body ----------------
const body=[];const front=[];
const add=(...x)=>body.push(...x);
front.push(new Paragraph({alignment:AlignmentType.CENTER,spacing:{after:240},children:[new TextRun({text:"TABLE OF CONTENTS",font:F,size:28,bold:true})]}));
front.push(new TableOfContents("Table of Contents",{hyperlink:true,headingStyleRange:"1-2"}));
// 1 INTRODUCTION
add(H1("1. INTRODUCTION"));
add(H2("1.1 Background"));
add(P("Every monsoon, rice (paddy) fields in Assam, Bihar and Odisha go under water. District officers then have to answer a simple question: **how much of the paddy in each village is flooded?** Relief, crop-insurance claims (for example under PMFBY) and field visits all depend on that answer. Today the answer comes either from slow field reports or from flood maps made centrally by national agencies, a few hundred a year for more than 700 districts [11]."));
add(P("In plain words, imagine a person looking down at the whole district from very high up. Satellite radar (Sentinel-1) can see through clouds, and water looks dark in a radar picture, so that person can point at places that “look flooded”. But it is still a guess. A river, a pond, a wet road and a flooded rice field can all look dark, and a rice field that is flooded but full of tall green plants can look dry. A map is a good first guess, not a measurement."));
add(P("So far we have built a first version of the project (then called EvidEO). It lets a person ask a plain question such as “How much of Barpeta was under water on 11 July 2024?”. It finds the right Sentinel-1 or Sentinel-2 scenes from public catalogues, measures the water with a transparent method, and returns an *evidence card* with a map, scene IDs, a confidence score and a receipt that re-runs the same analysis. It is working end to end. In our tests a whole district (117 tiles) takes 54 to 98 seconds on a CPU, 8 of 8 saved receipts re-ran to identical results, and the water confidence error fell from 0.139 to 0.074 on held-out hand-labelled chips (Sen1Floods11 [3])."));
add(P("The need is now concrete. The Government of India has brought paddy inundation back as a localised-calamity cover under PMFBY from Kharif 2026 [20]. Under the scheme’s operational guidelines, if the affected area of a notified crop is more than 25% of the insured area in a notified insurance unit (a village or village panchayat), all eligible farmers in the unit are deemed to have suffered localised loss, and the loss is assessed by a sample survey [19]. So the decision that matters is a yes or no on an area share, per unit, within days. We do not have access to insured-plot records, so we estimate the share of paddy area that was flooded, which is a proxy for the insured-area share."));
add(P("The most useful lesson came from the Barpeta result. The answer was 914 sq km of water, 39% of the 2,335 sq km measured. That number includes the Brahmaputra river, permanent wetlands and flooded paddy all mixed together, and it comes with no margin of error. An officer cannot act on “914 sq km of dark pixels”. They need “*about 34% of this village’s paddy was flooded, give or take 6%*”. A map on its own cannot give that; it needs a small amount of ground truth. This lesson is what shapes the moving-forward version of the project."));
add(H2("1.2 Problem Statement"));
add(P("The project started from the idea of an assistant that answers text questions about satellite images. The first version tried to cover many question types (floods, crop change, land cover). Moving forward we narrow it to one question and answer it properly:"));
add(new Paragraph({alignment:AlignmentType.JUSTIFIED,spacing:{line:360,after:160},indent:{left:567,right:567},border:{left:{style:BorderStyle.SINGLE,size:18,color:RED,space:8}},children:runs("*Given a flood event and a list of villages (or panchayats), estimate for each village the share of its paddy area that was flooded, with an honest margin of error, using satellite flood maps plus a small, well-chosen field sample. Then give the officer a call for every village (above or below the decision line, with the probability that the call is right) and say which plots to check next and by which road.*")}));
add(P("This is hard for four reasons:",{after:60,keepNext:true}));
add(B("**Maps make mistakes in both directions:** radar shadow, hills and roads create false water; flooded vegetation and urban areas are missed."));
add(B("**Counting pixels is biased:** if the map errs more one way than the other, the count of “flooded” pixels is wrong even when most pixels are right [14], [15]."));
add(B("**Field visits are expensive:** officers can check a few dozen plots, not thousands, so the checks must be chosen carefully."));
add(B("**Decisions need a line:** a village either crosses a relief or claim threshold or it does not (the legal line is 25% of area in a unit [19], and it is configurable in our design). A number with no error bar cannot settle that."));
add(P("The objectives of the project are:",{after:60,before:120,keepNext:true}));
add(N("Produce a per-pixel *chance of flooded* map from radar, terrain and permanent-water information, restricted to paddy plots.","obj"));
add(N("Estimate, for each village, the flooded share of paddy area with a margin of error, using a stratified random field sample.","obj"));
add(N("Call every village “above” or “below” the 25% line, together with the probability that the call is right. A village is never left undecided; a weak call is shown as a probability near 50%, not withheld.","obj"));
add(N("Plan the next field checks and the officers’ routes so that each check lowers the expected number of wrong calls the most, using the flood map to price travel on flooded roads.","obj"));
add(N("Wrap this in a simple tool: event board, village triage, survey plan, field entry and village dossier.","obj"));
add(P("The scope is kharif paddy during monsoon floods, with the Brahmaputra floodplain of Assam (Barpeta) as the pilot area, using free Sentinel-1 data. Yield-loss estimation, non-paddy crops and building a new foundation model are out of scope.",{before:120}));

// 2 LITERATURE SURVEY
add(H1("2. LITERATURE SURVEY"));
add(P("We reviewed work in five areas, from “how do we see water from space” to “how do we turn a map into a trustworthy number”. The first four are well studied; the fifth is where this project fits."));
add(H2("2.1 Mapping floods with radar"));
add(P("Radar sees water as dark because the water surface reflects the beam away from the satellite. Twele et al. [1] built a fully automated Sentinel-1 flood chain that picks a threshold tile by tile, adds a terrain filter (HAND) and uses fuzzy logic and region growing to clean the result. Tiwari et al. [2] applied automatic Otsu thresholding on Sentinel-1 VV to the Kerala 2018 flood and reached about 94.7% overall accuracy against Sentinel-2, which makes it a useful Indian reference. For learned methods, Sen1Floods11 [3] provides 11 flood events with hand-labelled Sentinel-1 chips, a standard benchmark for training U-Net style segmentation models [4]. In the monsoon, optical satellites are blocked by cloud: in three Western Ghats districts cloud cover averaged 90 to 92% in July and August, which is why radar is the main sensor for floods [13]."));
add(H2("2.2 False water and uncertainty"));
add(P("Many dark pixels are not flood. HAND (Height Above the Nearest Drainage) [5] tells how high a pixel sits above the nearest river, so high ground can be rejected as flood. Zhao et al. [6] build “exclusion maps” from radar time series that flag places where radar cannot see water reliably (shadow, layover, dense vegetation, sand). Giustarini et al. [7] go further and give each pixel a *probability* of being flooded instead of a hard yes or no, and check it with a reliability diagram. We take from these papers the idea that every pixel should carry a chance, not a verdict."));
add(H2("2.3 Paddy and flooded paddy in India"));
add(P("Singha et al. [8] mapped paddy at 10 m resolution across Bangladesh and Northeast India from Sentinel-1 VH time series with a random forest, at 94 to 98% overall accuracy per season, and Mohite et al. [9] showed operational near-real-time kharif rice mapping in Andhra Pradesh. Both give us a ready *rice mask*. Kumar et al. [10] combined Sentinel-1 and Sentinel-2 to map flood-affected paddy in Bihar in 2020, about 7,019 sq km submerged, with water standing on paddy for 50 to 65 days. Their work shows that how long the water stayed matters, and that the final numbers were validated only against other maps, not against a field sample. SICKLE [18] shows that ground-surveyed paddy plot datasets exist for India, which helps us design realistic tests."));
add(H2("2.4 Official systems"));
add(P("NRSC’s Flood Affected Area Atlas [11] classifies India by how often each place flooded over 25 years (1998 to 2022), and NDEM serves analyst-made flood sheets. Under PMFBY, the YES-TECH manual [12] makes satellite-derived yield estimates count for 30% of loss assessment. These systems work at state or district scale and deliver maps and statistics. None of them gives an officer a village-level flooded-paddy share with a stated margin of error and a plan for the next field visits."));
add(H2("2.5 Turning maps into trustworthy area numbers"));
add(P("This is the heart of the project. In land-cover mapping, Olofsson et al. [14], [15] showed that counting pixels in a map gives biased areas, and recommended a *stratified random sample* of reference observations to correct the map and to report a confidence interval. The classic survey-sampling theory behind it is in Cochran [16]. More recently, prediction-powered inference [17] formalised the same intuition for machine learning: use a large pile of cheap model predictions together with a small set of trusted labels to get valid estimates with honest intervals. In land-cover change this approach is established. We did not find it applied to **flooded paddy at village level, with a decision threshold and a field-sample planner**, which is the gap we target."));
add(H2("2.6 Summary and research gap"));
add(table([1800,2900,3951],[
 ["Area","Key works","What we take"],
 ["Radar flood mapping","Twele [1], Tiwari [2], Sen1Floods11 [3], U-Net [4]","Threshold method (built); labelled data and a U-Net to train"],
 ["False water, uncertainty","HAND [5], exclusion maps [6], probabilistic maps [7]","Terrain and permanent-water filters; per-pixel chance"],
 ["Paddy in India","Singha [8], Mohite [9], Kumar [10], SICKLE [18]","Rice mask; submergence duration; test ideas"],
 ["Official systems","NRSC atlas [11], YES-TECH [12]","The decision context and users"],
 ["Area estimation","Olofsson [14],[15], Cochran [16], PPI [17]","Stratified sample, corrected share and interval"],
]));
add(gap());
add(P("In short, flood maps are plentiful and well validated pixel by pixel, but the step from “map” to “village number an officer can act on, with an error bar” is missing, and nobody plans the field visits to make that number tighter. Closing that gap is the contribution of this project."));

// 3 DESIGN / METHODOLOGY
add(H1("3. DESIGN AND METHODOLOGY"));
add(H2("3.1 The idea in one picture"));
add(P("In plain words, the satellite guesses, a few people check, and a little maths joins the two. The guess is cheap and covers everything; the check is expensive and covers a little; the maths makes the small check tell us how wrong the big guess is. A second piece of maths decides where to check and which road to drive. Figure 1 shows the system in five layers. The layer count is fixed at five on purpose: more layers are harder to build and to explain."));
add(new Paragraph({alignment:AlignmentType.CENTER,keepNext:true,spacing:{before:120,after:60},children:[img("fig_layers.png",520,405)]}));
add(CAP("Figure 1. Five layers: Data and platform, Mapping, Estimation, Field planning, Tool."));
add(P("The two layers in the middle of the stack, Estimation and Field planning, are where the algorithmic contribution sits. They are the parts for which we have simulation results (Section 4). Layers 1 and 2 are mostly engineering that already exists, and the Tool layer is the part the officer touches."));
add(H2("3.2 Layer 1: Data and platform (mostly built)"));
add(P("This layer finds and reads satellite data and keeps every result reproducible."));
add(B("**Built:** STAC search of public catalogues, cloud-optimised GeoTIFF window reads, radar first in the monsoon, a FastAPI service with a job queue and workers, and receipts that store the scenes, windows and parameters so a result can be re-run to the same output."));
add(B("**To add:** insurance-unit (village or panchayat) boundaries, an OpenStreetMap road graph, and a record of revisit gaps (days since the last dry and the last wet pass). Receipts will also store the probability with which each field check was selected (Section 4.3)."));
add(H2("3.3 Layer 2: Mapping (the quick guess)"));
add(P("This layer is partly built and well understood. For each paddy pixel it produces a calibrated chance of being flooded."));
add(B("**Physics threshold (built):** Sentinel-1 VV/VH backscatter with an automatic per-tile threshold, calibrated on Sen1Floods11, with a slope and HAND terrain mask."));
add(B("**U-Net (to build):** a small segmentation network trained on Sen1Floods11 as a second opinion that can catch cases the threshold misses."));
add(B("**Priors:** permanent water, terrain and radar-exclusion layers remove the river and hills, so the count reflects *new* water. The rice mask [8], [9] keeps only paddy."));
add(B("**Fusion:** the threshold, the U-Net and the priors are combined per pixel into one chance of flooded, P(flooded), whose reliability is checked against labels [7]."));
add(B("**Submergence duration (idea, not yet built):** the satellite does not see the moment the water arrives. If a pixel was dry on one pass and wet on the next, the onset lies somewhere between the two, and the same holds for recession. Treating both as intervals gives a chance that the plot stayed under water for at least d days, which matters for crop damage [10]. We have not yet found a paper that reports paddy submergence duration with this kind of uncertainty, so this is a candidate idea to check carefully, not a claim."));
add(P("The output is a flooded-paddy probability map. The map is deliberately not required to be perfect; its job is to be informative enough that a small sample can correct it."));
add(H2("3.4 Layer 3: Estimation (the research contribution, part 1)"));
add(P("Instead of reporting the map’s count as the answer, we treat the map as a *sorting machine* and use a small field sample to measure how wrong it is. The steps for each village are:"));
add(N("**Stratify:** sort the village’s paddy plots into groups using the map (mapped flooded, mapped dry).","chk"));
add(N("**Sample:** pick a small number of plots at random inside each group.","chk"));
add(N("**Check:** field staff record flooded or not for each picked plot.","chk"));
add(N("**Correct:** weight each group’s sample result by the group’s share of plots to get the corrected flooded share and its standard error.","chk"));
add(N("**Call:** compare the corrected share with the 25% line and answer *above* or *below*. Every village gets a call. The call comes with the probability that it is right, so a village at 26% is answered “above, probability about 0.55” rather than left undecided.","chk"));
add(P("In symbols, for village u with map groups h (dry, flooded), group weights W_uh (the share of the village’s paddy plots in group h), n_uh checks of which k_uh were flooded, and the line τ = 0.25:",{before:120,keepNext:true}));
add(P("p_uh = (k_uh + m π_h) / (n_uh + m)",{align:AlignmentType.CENTER,after:40,keepNext:true}));
add(P("θ_u = Σ_h W_uh p_uh",{align:AlignmentType.CENTER,after:40,keepNext:true}));
add(P("s_u² = Σ_h W_uh² p_uh (1 − p_uh) / (n_uh + m + 1)",{align:AlignmentType.CENTER,after:40,keepNext:true}));
add(P("call_u = above if θ_u > τ, else below;   P_u = Φ((θ_u − τ) / s_u)",{align:AlignmentType.CENTER,after:120}));
add(P("Here π_h is the flooded rate in group h pooled over all villages, m is a prior strength that pulls a village with very few checks toward the pooled rate, and Φ is the normal distribution function. With no checks, θ_u is the raw map fraction. P_u is the chance the village is truly above the line, so it says how far to trust the call and never withholds it."));
add(P("Here is a worked example with illustrative numbers (not measured results), with m = 0 so the arithmetic is easy to follow. A village has 1,000 paddy plots. The map marks 300 as flooded and 700 as dry, so a raw count says 30%. We visit 100 plots:",{keepNext:true}));
add(table([1900,1250,1250,1450,1450,1351],[
 ["Map group","Plots in village","Plots visited","Found flooded","Share flooded","Weighted share"],
 ["Mapped flooded","300","30","27","90%","27.0%"],
 ["Mapped dry","700","70","7","10%","7.0%"],
 ["**Village total**","**1,000**","**100**","**34**","","**34.0%**"],
],{align:[AlignmentType.LEFT,AlignmentType.CENTER,AlignmentType.CENTER,AlignmentType.CENTER,AlignmentType.CENTER,AlignmentType.CENTER]}));
add(gap());
add(P("The standard error is 0.03 (3.0 points). The corrected share 34% is above 25%, so the call is **above**, and P = Φ((0.34 − 0.25)/0.03) = Φ(3.0), about 0.999. Notice two things. First, the corrected 34% is higher than the raw map’s 30%, because the map missed flooded plots hiding in the “dry” group; the check found and fixed that. Second, if we had visited the same 100 plots *without* using the map to sort them, the standard error would be 0.047 and P would be Φ(1.9), about 0.97. The map does not replace the field visits; it makes each visit worth more. (The finite-population correction is ignored, which only makes the error slightly larger.)"));
add(P("Farmer reports are treated as their own group: cheap but not random, so they are never mixed in silently. A planned extension reports, for each call, how strong a selection bias in the reports would have to be before the call flips."));
add(H2("3.5 Layer 4: Field planning (the research contribution, part 2)"));
add(P("The sample is small, so where to spend each check matters. The obvious rule is to put checks where the estimate is most uncertain. That lowers the error bar but not necessarily the number of wrong calls, because a village at 5% or 60% is already settled however wide its error bar is. Our rule targets the decision. For village u with distance d_u = θ_u − τ and error s_u, the chance that the current call is wrong is Φ(−|d_u| / s_u). One more check in group h lowers the error to s′ and moves the estimate to a new value d′, which is random with variance s_u² − s′². The expected gain from that check is"));
add(P("gain(u,h) = Φ(−|d_u|/s_u) − E over d′ ~ N(d_u, s_u² − s′²) of Φ(−|d′|/s′)",{align:AlignmentType.CENTER,after:120}));
add(P("The expectation is computed with a 15-point Gauss-Hermite rule. The next check goes to the village and group with the largest gain. Because the rule averages over the future estimate, it does not stall for a village sitting exactly on the line. The baseline it must beat is the usual variance-minimising rule, which picks the largest drop in total variance."));
add(P("Checks also cost driving time, and in a flood the roads are the thing that is flooded. The radar flood map therefore does two jobs: it estimates loss, and it prices travel. We build a road graph in which a flooded road segment takes 8 times its normal time, compute travel times with Dijkstra’s shortest-path algorithm, and give each officer a daily time limit. Choosing which villages to visit within that limit is an orienteering problem. We use a greedy rule: repeatedly insert the village with the highest gain per extra minute into the cheapest position in any officer’s route, and re-plan each morning."));
add(P("The planner also turns the loosely worded “requisite percentage of sample survey” in the guidelines [19] into a number: the checks needed to bring the expected share of wrong calls below a chosen level, and the order in which to visit."));
add(H2("3.6 Layer 5: Tool (what the officer sees)"));
add(table([2200,6451],[
 ["Screen","What it does (in plain words)"],
 ["Event board","Lists flood events and shows each event’s overall state on a map (built as the question wizard and evidence card, to be extended)."],
 ["Unit calls","One row per village: call (above or below), flooded share, probability, number of checks behind it. There is no “undecided” row."],
 ["Day route","Shows each officer’s route, flooded roads in blue, and the villages in visit order."],
 ["Field entry","A simple mobile-friendly form to record flooded or not for each visited plot, usable offline."],
 ["Village dossier","One page per village: corrected share, probability, map, sample, scene IDs and a receipt to re-run it."],
]));
add(gap());
add(H2("3.7 Why this is novel, and what we learn"));
add(P("Each ingredient is known. Combining a few trusted labels with many model predictions (prediction-powered inference) is published, including stratified versions on land-cover area [17], [21]. Choosing which labels to collect, with valid intervals, is also published as adaptive and active inference. We therefore do not claim a new estimator. Among the papers we read in full, none applies this to a radar flood map, targets a legal area-share threshold per insurance unit, and allocates field checks to minimise the expected number of wrong threshold calls across many units. The contribution is that combination, the allocation rule, and the flood-aware routing. This claim rests on a limited search and must be rechecked before submission. What we learn by building it:"));
add(B("How survey sampling and prediction-powered ideas work in practice, including when they fail."));
add(B("How much a map’s bias really matters, measured instead of assumed."));
add(B("How many field checks are needed for a decision, by village size and map quality."));
add(H2("3.8 Evaluation plan"));
add(P("We have no field survey of flooded paddy yet, so evaluation uses simulation first and labelled public data after that:"));
add(N("**Simulation (done, Section 4):** synthetic villages with their own true flooded share and their own map error, used to compare allocation rules and routes by the number of wrong 25% calls.","ev"));
add(N("**Mapping quality:** IoU and calibration error of the threshold, the U-Net and the fused map on Sen1Floods11 held-out chips.","ev"));
add(N("**Real-error check:** group Sen1Floods11 chips into pseudo-villages with whole regions held out, replace the synthetic map errors with real ones, and repeat the comparison. Until then every result stays labelled synthetic.","ev"));
add(N("**Pilot:** run the full pipeline on Barpeta (July 2024) with a synthetic sample, and, if possible, a small real sample from a partner.","ev"));

// 4 RESULTS
add(H1("4. PRELIMINARY RESULTS (SYNTHETIC)"));
add(P("All results in this section come from simulations in the folder research/threshold_alloc of the project repository. They use made-up villages, not real flood data, and they say nothing yet about real Sentinel-1 error. Pixels inside a village are treated as independent, which understates the real variance because flood errors cluster in space."));
add(H2("4.1 Wrong calls against field checks"));
add(P("The simulation has 200 villages of 1,500 paddy pixels each. Each village has its own true flooded share (mean 0.25) and its own map error (sensitivity about 0.75, false-positive rate about 0.08), so the map is biased differently in each village. Every method answers every village; only the way field checks are placed differs. The results are the mean of 60 runs. Table 1 gives the percentage of villages whose 25% call is wrong."));
add(CAP("Table 1. Wrong 25% calls (percent of villages) against field checks per village."));
add(table([2950,640,640,640,640,640,640,700],[
 ["Method","0","2","4","8","16","24","32"],
 ["Map only","15.8","15.8","15.8","15.8","15.8","15.8","15.8"],
 ["Field only (no map)","n/a","33.8","32.5","27.6","20.6","18.1","16.0"],
 ["Map + checks, equal split","n/a","18.7","19.9","19.6","16.0","13.1","11.9"],
 ["Map + checks, variance-minimising","n/a","18.4","18.9","15.7","13.9","11.8","10.9"],
 ["**Map + checks, decision-targeted**","n/a","18.7","17.4","**13.5**","**10.2**","**8.6**","**7.1**"],
],{align:[AlignmentType.LEFT,...Array(7).fill(AlignmentType.CENTER)]}));
add(gap());
add(new Paragraph({alignment:AlignmentType.CENTER,keepNext:true,spacing:{before:60,after:60},children:[img("../../figures/wrong_call_vs_checks.png",440,275)]}));
add(CAP("Figure 2. Wrong calls against field checks per village (synthetic, 200 villages, mean of 60 runs)."));
add(B("At 32 checks per village the decision-targeted rule makes about 40% fewer wrong calls than the equal split (7.1 against 11.9) and about 35% fewer than the variance-minimising rule (7.1 against 10.9). It reaches the equal split’s 32-check result with about 12 checks per village, roughly a third of the field effort."));
add(B("**At very small budgets (2 to 4 checks per village) every check-based method is worse than the raw map in this setup.** A handful of noisy checks adds more variance than it removes bias. The operating advice is to start from the map and let checks accumulate, and to show the number of checks behind each call."));
add(B("The Brier score of the stated probability P_u at 32 checks is 0.059 for the decision-targeted rule, 0.076 variance-minimising, 0.085 equal split and 0.120 map only (lower is better), so the stated probabilities are also better where checks are placed by the new rule."));
add(H2("4.2 Route-aware planning on a flooded road graph"));
add(P("Thirty villages sit on a 21 by 21 road grid. A smooth flood field raises each village’s flooded share and also slows the roads around it (flooded segments cost 8 times more). Three officers leave a depot each day with a 4-hour limit, and each visit makes 12 checks at 1.5 minutes each. Table 2 gives the wrong calls after each day, mean of 200 runs."));
add(CAP("Table 2. Wrong 25% calls (percent of villages) after each survey day, 3 officers."));
add(table([3550,720,620,620,620,720,880,861],[
 ["Planner","Day 0","1","2","3","4","Visits","Checks"],
 ["Nearest village first (flood-blind)","14.2","13.7","12.7","11.9","11.6","47","565"],
 ["Highest gain first, travel ignored","14.2","13.1","12.4","11.5","10.9","22","269"],
 ["Gain per minute, flood-blind roads","14.2","13.3","12.9","12.2","11.7","29","354"],
 ["**Gain per minute, flood-aware roads**","14.2","13.5","11.9","10.7","**9.7**","43","511"],
],{align:[AlignmentType.LEFT,...Array(7).fill(AlignmentType.CENTER)]}));
add(gap());
add(new Paragraph({alignment:AlignmentType.CENTER,keepNext:true,spacing:{before:60,after:60},children:[img("../../figures/route_example.png",330,330)]}));
add(CAP("Figure 3. One example day: flooded roads in blue, one colour per officer, village shade shows the value of a visit (synthetic)."));
add(B("After 4 days the flood-aware planner has about 2 points fewer wrong calls than nearest-first or flood-blind planning (9.7 against 11.6 and 11.7), and about a third fewer than the map alone. The run-to-run error is about 0.4 points, so the gaps are small."));
add(B("A plan made on the dry road map overruns the day on the real flooded roads and is no better than nearest-first. This is the case for feeding the radar flood map into the routing."));
add(H2("4.3 Learning the map calibration from routed checks"));
add(P("The routing simulation froze the pooled group rate π_h at its calibrated value. An earlier version that pooled the labels gathered along routes doubled the error of nearest-first (about 12% to about 25% wrong), because villages near the depot are not a random sample of the district. A real survey does not know π_h in advance, so we tested whether it can be learned from the checks. The prior starts deliberately wrong (0.15 for mapped dry and 0.55 for mapped flooded, against realised values near 0.08 and 0.75). The importance-weighted version randomises day 1 by drawing each village with a known probability q_v (proportional to its gain, with a floor of 0.05, about 3 villages expected), and estimates π_h with weights 1/q_v (the Hajek estimator). Table 3 gives wrong calls after day 4, mean of 100 runs, with a standard error of about 0.6 to 1.1 points."));
add(CAP("Table 3. Wrong calls after day 4 (percent) by how the map-calibration prior is obtained."));
add(table([4250,2100,2301],[
 ["Planner and prior","Wrong calls, day 4","Prior error (mean absolute)"],
 ["Nearest first, frozen at the wrong start","14.1","0.125"],
 ["Nearest first, pooled naively from all checks","19.3","0.070"],
 ["Nearest first, oracle prior (not available in practice)","13.6","0.000"],
 ["Gain-aware, frozen at the wrong start","12.2","0.125"],
 ["Gain-aware, pooled naively from all checks","16.4","0.080"],
 ["Gain-aware, importance-weighted day-1 sample","17.9","0.130"],
 ["Gain-aware, oracle prior (not available in practice)","11.2","0.000"],
],{align:[AlignmentType.LEFT,AlignmentType.CENTER,AlignmentType.CENTER]}));
add(gap());
add(P("This did **not** work as hoped, and we report it as it is. After day 1 both the weighted and the naive estimates of the prior are close to unbiased (the weighted estimate is off by −0.002 for mapped dry and −0.02 for mapped flooded), but both are very noisy: the root-mean-square error for the mapped-flooded group is about 0.25 to 0.28, because only a handful of villages and flooded-group checks are available. Learning the prior from a few routed checks therefore hurts, and a prior left at its (wrong) start does better than either learned version. The bias seen in the earlier exploratory run builds up over later, adaptive days, which a day-1 probability sample does not use. The practical conclusion is that the calibration prior should come from labelled events (Sen1Floods11, Kuro Siwo), as already planned, and field checks should update individual villages, not the shared prior. We make no claim about the stated probabilities P_u under routed sampling beyond this."));
add(H2("4.4 Limits"));
add(B("Everything above is synthetic, with independent pixels inside a village; spatial clustering will widen the errors."));
add(B("With few checks per village a check-based estimate can be worse than the raw map (seen at 2 to 4 checks)."));
add(B("The routing result assumes a complete road graph; road data in rural India is patchy."));
add(B("In the importance-weighted run about a quarter of the villages drawn on day 1 were not reached in time, so the nominal inclusion probabilities are not exactly the realised ones."));
add(B("The novelty statement rests on a limited literature search, mostly at abstract level for the newest work."));

// 5 PROGRESS
add(H1("5. PROGRESS AND PLAN TO THE FINAL REVIEW"));
add(P("The Final Review is tentatively in the second week of December 2026, by which point 100% of the implementation and a complete report draft are expected. Status and proposed plan:"));
add(table([3300,3300,2051],[
 ["Item","Status","When"],
 ["Data layer, Sentinel-1/2 search, tiling, receipts","Done","Complete"],
 ["Physics threshold, calibration, terrain mask","Done (terrain mask shipped, off by default)","Complete"],
 ["Allocation and routing simulations (Section 4)","Done, synthetic","Complete"],
 ["Rice mask and village boundaries, road graph","To do","16–22 Nov"],
 ["Estimation layer in the codebase (stratify, correct, call, probability)","To do","16–29 Nov"],
 ["Simulation on Sen1Floods11 chips grouped into villages","To do","23–29 Nov"],
 ["U-Net and per-pixel fusion, submergence duration","To do","23 Nov–6 Dec"],
 ["Tool screens (unit calls, day route, field entry, dossier)","To do","30 Nov–6 Dec"],
 ["Integration, Barpeta pilot, full report","To do","7–11 Dec"],
]));
add(gap());
add(new Paragraph({heading:HeadingLevel.HEADING_1,pageBreakBefore:true,children:[new TextRun({text:"REFERENCES",font:F})]}));
const refs=[
"A. Twele, W. Cao, S. Plank and S. Martinis, “Sentinel-1-based flood mapping: a fully automated processing chain,” Int. J. Remote Sensing, 37(13), pp. 2990–3004, 2016.",
"V. Tiwari et al., “Flood inundation mapping, Kerala 2018: harnessing the power of SAR, automatic threshold detection method and Google Earth Engine,” PLOS ONE, 15(8): e0237324, 2020.",
"D. Bonafilia, B. Tellman, T. Anderson and E. Issenberg, “Sen1Floods11: a georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1,” CVPR Workshops, 2020.",
"O. Ronneberger, P. Fischer and T. Brox, “U-Net: convolutional networks for biomedical image segmentation,” MICCAI, 2015.",
"A. D. Nobre et al., “Height Above the Nearest Drainage: a hydrologically relevant new terrain model,” J. Hydrology, 404(1–2), pp. 13–29, 2011.",
"J. Zhao et al., “Deriving exclusion maps from C-band SAR time-series in support of floodwater mapping,” Remote Sensing of Environment, 265, 112668, 2021.",
"L. Giustarini et al., “Probabilistic flood mapping using synthetic aperture radar data,” IEEE Trans. Geosci. Remote Sens., 54(12), pp. 6958–6969, 2016.",
"M. Singha, J. Dong, G. Zhang and X. Xiao, “High resolution paddy rice maps in cloud-prone Bangladesh and Northeast India using Sentinel-1 data,” Scientific Data, 6, Article 26, 2019.",
"J. D. Mohite et al., “Operational near real time rice area mapping using multi-temporal Sentinel-1 SAR observations,” ISPRS Archives, XLII-4, pp. 433–438, 2018.",
"H. Kumar, S. K. Karwariya and R. Kumar, “Google Earth Engine-based identification of flood extent and flood-affected paddy rice fields using Sentinel-2 MSI and Sentinel-1 SAR data in Bihar State, India,” J. Indian Soc. Remote Sensing, 50, pp. 791–803, 2022.",
"National Remote Sensing Centre (ISRO), “Flood Affected Area Atlas of India: satellite based study,” released March 2023 (NDEM).",
"Mahalanobis National Crop Forecast Centre, “Yield Estimation System based on Technology (YES-TECH) under PMFBY: manual for implementation,” Ministry of Agriculture and Farmers Welfare, Jan. 2023.",
"G. Uday et al., “Radar versus optical: the impact of cloud cover when mapping seasonal surface water for health applications in monsoon-affected India,” PLOS ONE, 20(1): e0314033, 2025.",
"P. Olofsson et al., “Making better use of accuracy data in land change studies: estimating accuracy and area and quantifying uncertainty using stratified estimation,” Remote Sensing of Environment, 129, pp. 122–131, 2013.",
"P. Olofsson et al., “Good practices for estimating area and assessing accuracy of land change,” Remote Sensing of Environment, 148, pp. 42–57, 2014.",
"W. G. Cochran, *Sampling Techniques*, 3rd ed., Wiley, 1977.",
"A. N. Angelopoulos et al., “Prediction-powered inference,” Science, 382(6671), pp. 669–674, 2023.",
"D. Sani et al., “SICKLE: a multi-sensor satellite imagery dataset annotated with multiple key cropping parameters,” IEEE/CVF WACV, pp. 5983–5992, 2024.",
"Department of Agriculture, Cooperation and Farmers Welfare, “Operational Guidelines, Pradhan Mantri Fasal Bima Yojana (Revised),” Ministry of Agriculture and Farmers Welfare, Government of India, 2018.",
"Press Information Bureau, Ministry of Agriculture and Farmers Welfare, “Paddy inundation reintroduced under localised calamity, to be rolled out from Kharif 2026,” release 2191224, 18 Nov. 2025.",
"K. Lu, D. M. Kluger, S. Bates and S. Wang, “Regression coefficient estimation from remote sensing maps,” arXiv:2407.13659, v7, 2025.",
];
refs.forEach((r,i)=>add(new Paragraph({alignment:AlignmentType.JUSTIFIED,spacing:{line:300,after:100},indent:{left:540,hanging:540},children:[new TextRun({text:`[${i+1}]\t`,font:F,size:24}),...runs(r)]})));

const hs=(sz,bold,italics,align,before,after)=>({run:{font:F,size:sz,bold,italics,color:"000000"},paragraph:{alignment:align,spacing:{before,after,line:360},keepNext:true,keepLines:true}});
const doc=new Document({
  creator:"RVITM Dept. of CSE",title:"Paddybird Partial Mini Project Report",
  styles:{default:{document:{run:{font:F,size:24}}},
    paragraphStyles:[
      {id:"TOC1",name:"toc 1",basedOn:"Normal",next:"Normal",run:{font:F,size:24,bold:true},paragraph:{spacing:{before:120,after:40}}},
      {id:"TOC2",name:"toc 2",basedOn:"Normal",next:"Normal",run:{font:F,size:24},paragraph:{spacing:{before:0,after:40},indent:{left:360}}},
      {id:"Heading1",name:"Heading 1",basedOn:"Normal",next:"Normal",quickFormat:true,...hs(28,true,false,AlignmentType.CENTER,360,200),paragraph:{alignment:AlignmentType.CENTER,spacing:{before:360,after:200,line:360},keepNext:true,keepLines:true,outlineLevel:0}},
      {id:"Heading2",name:"Heading 2",basedOn:"Normal",next:"Normal",quickFormat:true,run:{font:F,size:24,bold:true,color:"000000"},paragraph:{alignment:AlignmentType.LEFT,spacing:{before:240,after:120,line:360},keepNext:true,keepLines:true,outlineLevel:1}},
      {id:"Heading3",name:"Heading 3",basedOn:"Normal",next:"Normal",quickFormat:true,run:{font:F,size:24,bold:true,italics:true,color:"000000"},paragraph:{alignment:AlignmentType.LEFT,spacing:{before:200,after:100},keepNext:true,outlineLevel:2}},
    ]},
  numbering:{config:[
    {reference:"bul",levels:[{level:0,format:LevelFormat.BULLET,text:"•",alignment:AlignmentType.LEFT,style:{paragraph:{indent:{left:720,hanging:360}}}}]},
    ...["num","obj","chk","ev"].map(r=>({reference:r,levels:[{level:0,format:LevelFormat.DECIMAL,text:"%1.",alignment:AlignmentType.LEFT,style:{paragraph:{indent:{left:720,hanging:360}}}}]})),
  ]},
  sections:[
    {properties:{titlePage:true,page:{size:{width:11900,height:16840},margin:{top:1077,bottom:1077,left:1809,right:1440,header:709,footer:709},
        pageNumbers:{start:1,formatType:D.NumberFormat.UPPER_ROMAN},
        borders:{pageBorders:{display:D.PageBorderDisplay.ALL_PAGES,offsetFrom:D.PageBorderOffsetFrom.PAGE},
          pageBorderTop:{style:BorderStyle.SINGLE,size:6,color:"000000",space:24},pageBorderBottom:{style:BorderStyle.SINGLE,size:6,color:"000000",space:24},
          pageBorderLeft:{style:BorderStyle.SINGLE,size:6,color:"000000",space:24},pageBorderRight:{style:BorderStyle.SINGLE,size:6,color:"000000",space:24}}}},
     headers:{default:new D.Header({children:[new Paragraph({children:[]})]}),first:new D.Header({children:[new Paragraph({children:[]})]})},
     footers:{default:mkFooter(),first:new Footer({children:[new Paragraph({children:[]})]})},
     children:[...cover,new Paragraph({children:[new PageBreak()]}),...front]},
    {properties:{page:{size:{width:11900,height:16840},margin:{top:1077,bottom:1077,left:1809,right:1440,header:709,footer:709},pageNumbers:{start:1,formatType:D.NumberFormat.DECIMAL}}},
     headers:{default:mkHeader()},footers:{default:mkFooter()},children:body},
  ]});
Packer.toBuffer(doc).then(b=>{fs.writeFileSync('report_raw.docx',b);console.log('ok')});
