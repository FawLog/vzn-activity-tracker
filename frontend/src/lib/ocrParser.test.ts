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
