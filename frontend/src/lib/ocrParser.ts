import type { OcrPreview } from "./api";

export type ParsedRow = { nickname: string; damage?: number; source: string };
type Word = { text: string; x: number; y: number; right: number; height: number };
type Line = { words: Word[]; y: number; height: number };
export const normalizeName = (name:string) => name.normalize("NFC").trim().replace(/^\s*\[[^\]]+\]\s*/, "").replace(/\s+/g," ").toLowerCase();
const lineText = (line:Line) => line.words.map(w=>w.text).join(" ");
function linesFrom(preview:OcrPreview):Line[] {
  const words:Word[] = preview.tokens.flatMap(t=>{
    if(t.vertices.length!==4 || !t.text.trim())return [];
    const xs=t.vertices.map(v=>v.x),ys=t.vertices.map(v=>v.y);
    return [{text:t.text,x:Math.min(...xs),right:Math.max(...xs),y:(Math.min(...ys)+Math.max(...ys))/2,height:Math.max(1,Math.max(...ys)-Math.min(...ys))}];
  }).sort((a,b)=>a.y-b.y);
  const lines:Line[]=[];
  for(const w of words){
    const line=lines.find(l=>Math.abs(l.y-w.y)<=Math.max(3,Math.min(l.height,w.height)*.55));
    if(line){line.words.push(w);line.height=Math.max(line.height,w.height)}else lines.push({words:[w],y:w.y,height:w.height});
  }
  for(const l of lines)l.words.sort((a,b)=>a.x-b.x);
  return lines.sort((a,b)=>a.y-b.y);
}
function numberFrom(text:string):number|undefined {
  const cleaned=text.trim().replace(/\s/g,"");
  if(!/^(?:\d+|\d{1,3}(?:,\d{3})+)$/.test(cleaned))return;
  const n=Number(cleaned.replaceAll(",",""));
  return Number.isSafeInteger(n)&&n>=0?n:undefined;
}
export function parseScreenshot(preview:OcrPreview,eventType:string,sessionKey:string,source:string):{rows:ParsedRow[];warnings:string[]} {
  const lines=linesFrom(preview), rows:ParsedRow[]=[],warnings:string[]=[];
  if(!lines.length)return {rows,warnings:["No word coordinates; inspect the original screenshot and raw text."]};
  if(eventType==="bear_trap"){
    const heading=lines.find(l=>/Trap\s*[12]\s*Damage\s*Rewards/i.test(lineText(l)));
    const trap=heading&&lineText(heading).match(/Trap\s*([12])/i)?.[1];
    if(!trap||sessionKey!=="trap_"+trap)return {rows,warnings:["Trap header is missing or does not match the selected session."]};
    const header=lines.find(l=>l.y>heading!.y&&/Ranking/i.test(lineText(l))&&/Damage\s*Points/i.test(lineText(l)));
    if(!header)return {rows,warnings:["Damage ranking header not found."]};
    for(let i=0;i<lines.length;i++){
      const l=lines[i];if(l.y<=header.y)continue;
      const text=lineText(l);
      const match=text.match(/Damage\s*Points\s*:\s*(.+)$/i);
      if(!match)continue;
      const damage=numberFrom(match[1]);
      const previous=lines[i-1];
      const label=l.words.find(w=>/^Damage/i.test(w.text));
      if(damage===undefined||!previous||previous.y<=header.y||!label){warnings.push("Unreadable damage row: "+text);continue}
      const name=previous.words.filter(w=>w.right>=label.x-previous.height*.5&&w.x>=label.x-previous.height).map(w=>w.text).join(" ").replace(/^\s*\[[^\]]+\]\s*/,"").trim();
      if(!name||previous.y===l.y||l.y-previous.y>Math.max(l.height,previous.height)*3.5||/Damage Points/i.test(name)){warnings.push("Cannot associate damage with a nickname: "+text);continue}
      // The pinned unranked self row is not leaderboard evidence.
      const nearby=lines.filter(n=>Math.abs(n.y-previous.y)<=previous.height*2).flatMap(n=>n.words.filter(w=>w.right<label.x-previous.height).map(w=>w.text)).join(" ");
      if(/un\s*ran\s*ked|unran\s*ked/i.test(nearby)||damage===0){warnings.push("Skipped zero/unranked row: "+name);continue}
      rows.push({nickname:name,damage,source});
    }
  }else if(eventType==="alliance_championship"){
    const header=lines.find(l=>/Registered\s*:\s*\d+\s*\/\s*\d+/i.test(lineText(l)));
    if(!header)return {rows,warnings:["Registration list header not found; use a screenshot showing Registered: x/y."]};
    for(let i=1;i<lines.length;i++){
      const l=lines[i];if(l.y<=header.y)continue;
      const rank=l.words.find(w=>/^R[1-5]$/i.test(w.text));
      if(!rank)continue;
      const prev=lines[i-1];
      if(prev.y<=header.y||l.y-prev.y>Math.max(l.height,prev.height)*3.5)continue;
      // A complete row needs the rank and its numeric right-hand column.
      const numeric=lines.filter(n=>Math.abs(n.y-(prev.y+l.y)/2)<=Math.max(l.height,prev.height)*1.2).flatMap(n=>n.words).find(w=>w.x>rank.x+rank.height*6&&numberFrom(w.text)!==undefined);
      if(!numeric){warnings.push("Registration row has no readable right-hand value.");continue}
      const name=prev.words.filter(w=>w.x>=rank.x-rank.height&&w.right<numeric.x).map(w=>w.text).join(" ").trim();
      if(name&&!/^R[1-5]$/i.test(name))rows.push({nickname:name,source});
      else warnings.push("Cannot associate registration rank with a nickname.");
    }
  }
  if(!rows.length)warnings.push("No complete player rows recognized. Check the screenshot and raw text.");
  return {rows,warnings};
}
