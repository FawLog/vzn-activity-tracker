import { describe,it,expect } from "vitest";
import { parseScreenshot } from "./ocrParser";
import type { OcrPreview } from "./api";
function fixture(words:[string,number,number,number][]):OcrPreview {
 return {provider:"google_vision",text:"",warnings:[],tokens:words.map(([text,x,y,w])=>({text,vertices:[{x,y},{x:x+w,y},{x:x+w,y:y+20},{x,y:y+20}]}))};
}
describe("screenshot layouts",()=>{
 it("reads Bear scores above 32-bit range and ignores zero self row",()=>{
  const preview=fixture([["Trap 1 Damage Rewards",185,310,340],["Ranking",110,462,90],["Damage Points",296,462,160],["[VZN]NOVA EBRU",266,528,220],["Damage Points:4,515,319,571",266,570,350],["[VZN]Ultron",266,928,160],["Damage Points:3,540,340,242",266,970,350],["Unran",70,1198,60],["ked",80,1220,40],["[VZN]Piro",266,1198,170],["Damage Points:0",266,1240,180]]);
  expect(parseScreenshot(preview,"bear_trap","trap_1","bear").rows).toEqual([{nickname:"NOVA EBRU",damage:4515319571,source:"bear"},{nickname:"Ultron",damage:3540340242,source:"bear"}]);
  expect(parseScreenshot(preview,"bear_trap","trap_2","bear").rows).toEqual([]);
 });
 it("reads championship names, ignores rank and numeric value, rejects clipped rows",()=>{
  const preview=fixture([["Registered: 89/60",238,552,240],["Léo2025",132,618,100],["4,886",490,640,70],["R3",132,660,30],["KaraCentauri",132,730,150],["3,791",490,750,70],["R3",132,772,30],["Clipped name",132,840,140]]);
  expect(parseScreenshot(preview,"alliance_championship","main","champ").rows).toEqual([{nickname:"Léo2025",source:"champ"},{nickname:"KaraCentauri",source:"champ"}]);
 });
});

 it("reads Russian registration header and rank",()=>{
 const preview=fixture([["Зарегистрировано: 89/60",238,552,240],["Léo2025",132,618,100],["4 886",490,640,70],["Р3",132,660,30]]);
 expect(parseScreenshot(preview,"alliance_championship","main","ru").rows).toEqual([{nickname:"Léo2025",source:"ru"}]);
 });
 it("reads ordinary mobilization row with Russian missions label",()=>{
 const preview=fixture([["Рейтинг",68,840,100],["Личные очки",470,840,170],["[VZN]NOVA EBRU",262,900,200],["11 353",565,920,70],["Задания: 23/23",262,940,170]]);
 expect(parseScreenshot(preview,"alliance_mobilization","main","ru").rows).toEqual([{nickname:"NOVA EBRU",completed:23,total:23,points:11353,source:"ru"}]);
 });

 it("reads all eleven championship rows from reconstructed IMG_9215 geometry, including offset Piro",()=>{
 const names=["相忘於江湖","Mehmetylmzs","Piro","TENRİKENosm","CHAPO INFINITY X","BaRda AzReal","Zackeri Ma'at","Saint Erken","DarksideAMK","watermelon","Harissa"];
 const scores=["4,252","4,210","4,056","4,040","3,999","3,933","3,909","3,798","3,797","3,756","3,724"];
 const words:[string,number,number,number][]=[];
 names.forEach((name,i)=>{const y=222+i*111;words.push([name,i===2?171:132,y,Math.max(40,name.length*10)],[scores[i],490,y+22,68],[i===2||i===4||i===6?"R4":"R3",132,y+43,30]);if(i===2)words.push(["e",224,y-9,9]);});
 const parsed=parseScreenshot(fixture(words),"alliance_championship","main","IMG_9215");
 expect(parsed.rows.map(r=>r.nickname)).toEqual(names.map(n=>n==="Piro"?"Piro e":n));
 expect(parsed.warnings).toContain("Registration rows: 11 of 11 detected rank anchors; verify against the screenshot.");
 });
 it("warns about an incomplete rank row instead of borrowing another player's name",()=>{
 const parsed=parseScreenshot(fixture([["Alice",132,200,50],["4,200",490,222,65],["R3",132,243,30],["R4",132,354,30],["4,000",490,333,65]]),"alliance_championship","main","partial");
 expect(parsed.rows.map(r=>r.nickname)).toEqual(["Alice"]);expect(parsed.warnings.some(w=>w.includes("Skipped registration row"))).toBe(true);
 });

it("reads both Trap 2 pages reconstructed from IMG_9241 and IMG_9242 despite intervening avatar OCR",()=>{
 const names=["Léo2025","watermelon","CHAPO INFINITY X","乂 T KsA 乂","Lord NFSIEBEN","Ziggy","FALCON","송하민","KIRIKOU","EvlShrine"];
 const scores=["1,722,932,279","1,439,690,691","1,266,109,431","1,225,290,455","1,193,698,822","957,615,012","826,113,813","542,642,275","105,882,063","102,971,137"];
 for(let page=0;page<2;page++){
   const words:[string,number,number,number][]=[["Trap 2 Damage Rewards",185,310,340],["Ranking",110,462,90],["Damage Points",296,462,160]];
   for(let i=0;i<5;i++){
     const index=page*5+i,y=528+i*133;
     words.push([String(index+1),85,y+14,24],["[",266,y,8],["VZN",275,y,37],["]",313,y,8],[names[index],323,y,Math.min(270,names[index].length*11)],
       ["avatar",175,y+30,65],["Damage",266,y+42,85],["Points",354,y+42,60],[":",415,y+42,5],[scores[index],422,y+42,195]);
   }
   words.push(["Unran",70,1198,60],["ked",80,1220,40],["[VZN]Piro",266,1198,170],["Damage Points:0",266,1240,180]);
   const parsed=parseScreenshot(fixture(words),"bear_trap","trap_2","page"+page);
   expect(parsed.rows).toEqual(names.slice(page*5,page*5+5).map((nickname,i)=>({nickname,damage:Number(scores[page*5+i].replaceAll(",","")),source:"page"+page})));
   expect(parsed.warnings).toContain("Bear damage rows: 5 of 5 detected non-zero damage anchors; verify against the screenshot.");
 }
});
it("never borrows the preceding Bear nickname when a later row is missing",()=>{
 const parsed=parseScreenshot(fixture([["Trap 2 Damage Rewards",185,310,340],["Ranking",110,462,90],["Damage Points",296,462,160],["[VZN]Alice",266,528,140],["Damage Points:100",266,570,240],["7",85,650,24],["Damage Points:200",266,703,240]]),"bear_trap","trap_2","partial");
 expect(parsed.rows).toEqual([{nickname:"Alice",damage:100,source:"partial"}]);
 expect(parsed.warnings.some(w=>w.includes("Cannot associate damage"))).toBe(true);
});


it("reads main/substitute sections and counts without treating right-hand power as points",()=>{
 const parsed=parseScreenshot(fixture([["Combatants: 1/30",250,200,250],["Alpha",155,270,100],["1,899",570,290,80],["R4",155,310,30],["Substitutes: 1/10",250,390,250],["Beta",155,450,100],["2,890",570,470,80],["R0",155,490,30]]),"foundry_registration","legion_2","registration");
 expect(parsed.foundry).toEqual({main_count:1,substitute_count:1});
 expect(parsed.rows).toEqual([{nickname:"Alpha",role:"main",source:"registration"},{nickname:"Beta",role:"substitute",source:"registration"}]);
});
it("keeps cropped registration role unresolved and rejects wrong legion",()=>{
 const words:[string,number,number,number][]=[["Alpha",155,270,100],["1,899",570,290,80],["R4",155,310,30]];
 expect(parseScreenshot(fixture(words),"foundry_registration","legion_2","crop").rows).toEqual([{nickname:"Alpha",source:"crop"}]);
 expect(parseScreenshot(fixture([["Legion 1",100,80,100],...words]),"foundry_registration","legion_2","wrong").rows).toEqual([]);
});
it("reads explicit zero and personal score, excluding tally MVP and supporting medals without text",()=>{
 const words:[string,number,number,number][]=[["Legion Tally",280,100,200],["MVP",210,155,50],["Not a personal result",305,150,230],["72,818",305,190,90],["Personal Arsenal Points",220,270,310],["Alpha",306,340,100],["1,306,727",306,390,130],["2",80,520,20],["Beta",306,500,100],["678,058",306,550,100],["3",80,680,20],["Gamma",306,660,100],["0",306,710,20]];
 // Fixture font height is 20 px, with numeric rank offset from the nickname.
 const parsed=parseScreenshot(fixture(words),"foundry_results","legion_2","results");
 expect(parsed.rows.map(r=>[r.nickname,r.points])).toEqual([["Alpha",1306727],["Beta",678058],["Gamma",0]]);
 expect(parseScreenshot(fixture(words.slice(0,4)),"foundry_results","legion_2","tally").rows).toEqual([]);
});
it("reads a reviewed team summary without creating player results",()=>{
 const parsed=parseScreenshot(fixture([["Legion 2",60,80,100],["DEFEAT!",340,150,145],["#4284",170,190,65],["#4271",570,190,65],["[AAA]Alpha",100,230,200],["[BBB]Beta",500,230,180],["254,292",180,280,100],["263,311",575,280,100],["Legion Tally",300,340,180]]),"foundry_results","legion_2","summary");
 expect(parsed.rows).toEqual([]);
 expect(parsed.foundry).toEqual({outcome:"defeat",own_score:254292,opponent_score:263311,opponent_tag:"BBB",opponent_name:"Beta",opponent_state:"4271"});
});


// Reconstructed from the officer's in-game dialog screenshots, not live Vision output.
const combatantHeader=(legion=1,main=30,subs=10):[string,number,number,number][]=>[
 ["Legion",246,358,100],[String(legion),350,358,18],["Combatants",376,358,200],
 ["Join",235,468,49],["Substitute",551,468,126],
 [String(main),201,505,30],["/",232,505,9],["30",242,505,30],
 [String(subs)+"/10",562,505,70],["Troop",69,580,67],["Power",141,580,69],["45,296",519,580,92]
];
const combatantFooter:[string,number,number,number]=["Participants only",333,1204,234];
it("reads mixed Join and Substitute rows from the new Legion 1 screenshot, ignoring vote, rank and power",()=>{
 const words:[string,number,number,number][]=[...combatantHeader(),["1,891",222,630,65],
 ["Harissa",187,729,103],["1,866",222,773,65],["Join",701,749,51],
 ["FTAO0Y",187,879,126],["1,747",222,923,65],["Voted",678,849,61],["Substitute",628,899,124],
 ["M&R",187,1028,65],["1,723",222,1072,65],["Join",701,1048,51],
 ["R3",75,1131,28],["Rank 3",146,1131,80],["16/82",629,1131,67],combatantFooter];
 const parsed=parseScreenshot(fixture(words),"foundry_registration","legion_1","dialog");
 expect(parsed.foundry).toEqual({main_count:30,substitute_count:10});
 expect(parsed.rows).toEqual([{nickname:"Harissa",role:"main",source:"dialog"},{nickname:"FTAO0Y",role:"substitute",source:"dialog"},{nickname:"M&R",role:"main",source:"dialog"}]);
 expect(parseScreenshot(fixture(words),"foundry_registration","legion_2","wrong").rows).toEqual([]);
 expect(parseScreenshot(fixture(words),"foundry_results","legion_1","wrong-stage").rows).toEqual([]);
});
it("recognizes zero substitutes, split nickname tokens and non-Latin names; skips a clipped row",()=>{
 const words:[string,number,number,number][]=[...combatantHeader(2,18,0),
 ["Join",701,646,51],["1,999",222,669,65],
 ["Melon",187,729,70],["doggo",261,729,65],["1,409",222,771,65],["Join",701,749,51],
 ["北極熊",187,879,94],["1,596",222,921,65],["Join",701,899,51],
 ["Voted",677,1030,61],["Join",701,1050,51],combatantFooter];
 const parsed=parseScreenshot(fixture(words),"foundry_registration","legion_2","dialog");
 expect(parsed.foundry).toEqual({main_count:18,substitute_count:0});
 expect(parsed.rows).toEqual([{nickname:"Melon doggo",role:"main",source:"dialog"},{nickname:"北極熊",role:"main",source:"dialog"}]);
 expect(parsed.warnings.some(w=>w.includes("missing or ambiguous nickname"))).toBe(true);
});
it("requires a verifiable legion and complete dialog bounds rather than guessing a mail layout",()=>{
 const words:[string,number,number,number][]=[...combatantHeader(),["Harissa",187,729,103],["1,866",222,773,65],["Join",701,749,51],combatantFooter];
 expect(parseScreenshot(fixture(words.slice(3)),"foundry_registration","legion_1","no-title").rows).toEqual([]);
 expect(parseScreenshot(fixture(words.slice(0,-1)),"foundry_registration","legion_1","no-footer").rows).toEqual([]);
});
