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
