import type { OcrPreview } from "./api";

export type ParsedRow = { nickname: string; damage?: number; completed?: number; total?: number; points?: number; source: string };
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
  const cleaned=text.trim().replace(/[\s\u00a0\u202f]/g,"");
  if(!/^(?:\d+|\d{1,3}(?:,\d{3})+)$/.test(cleaned))return;
  const n=Number(cleaned.replaceAll(",",""));
  return Number.isSafeInteger(n)&&n>=0?n:undefined;
}
export function parseScreenshot(preview:OcrPreview,eventType:string,sessionKey:string,source:string):{rows:ParsedRow[];warnings:string[]} {
  const lines=linesFrom(preview), rows:ParsedRow[]=[],warnings:string[]=[];
  if(!lines.length)return {rows,warnings:["No word coordinates; inspect the original screenshot and raw text."]};
  if(eventType==="bear_trap"){
    const heading=lines.find(l=>/(?:Trap\s*[12]\s*Damage\s*Rewards|(?:ловушк[аеиу]|капкан)\s*[12])/iu.test(lineText(l)));
    const trap=heading&&lineText(heading).match(/(?:Trap|ловушк[аеиу]|капкан)\s*([12])/iu)?.[1];
    if(trap&&sessionKey!=="trap_"+trap)warnings.push("Verify host and local trap number: screenshot numbering may differ from group cycle numbering.");
    if(!trap)warnings.push("Trap number not visible: verify selected session manually.");
    const header=lines.find(l=>l.y>(heading?.y??-1)&&/(?:Ranking|рейтинг|место)/iu.test(lineText(l))&&/(?:Damage\s*Points|урон)/iu.test(lineText(l)));
    if(!header)warnings.push("Ranking header not visible; verify screenshot type manually.");
    for(let i=0;i<lines.length;i++){
      const l=lines[i];if(l.y<=(header?.y??-1))continue;
      const text=lineText(l);
      const match=text.match(/(?:Damage\s*Points|(?:очки\s+)?урона?)\s*:\s*(.+)$/iu);
      if(!match)continue;
      const damage=numberFrom(match[1]);
      const previous=lines[i-1];
      const label=l.words.find(w=>/^(?:Damage|очки|урон)/iu.test(w.text));
      if(damage===undefined||!previous||previous.y<=(header?.y??-1)||!label){warnings.push("Unreadable damage row: "+text);continue}
      const name=previous.words.filter(w=>w.right>=label.x-previous.height*.5&&w.x>=label.x-previous.height).map(w=>w.text).join(" ").replace(/^\s*\[[^\]]+\]\s*/,"").trim();
      if(!name||previous.y===l.y||l.y-previous.y>Math.max(l.height,previous.height)*3.5||/Damage Points/i.test(name)){warnings.push("Cannot associate damage with a nickname: "+text);continue}
      // The pinned unranked self row is not leaderboard evidence.
      const nearby=lines.filter(n=>Math.abs(n.y-previous.y)<=previous.height*2).flatMap(n=>n.words.filter(w=>w.right<label.x-previous.height).map(w=>w.text)).join(" ");
      if(/un\s*ran\s*ked|unran\s*ked/i.test(nearby)||damage===0){warnings.push("Skipped zero/unranked row: "+name);continue}
      rows.push({nickname:name,damage,source});
    }
  }else if(eventType==="alliance_championship"){
    const header=lines.find(l=>/(?:Registered|зарегистрирован[оы]?|регистрация)\s*:\s*\d+\s*\/\s*\d+/iu.test(lineText(l)));
    if(!header)warnings.push("Registration header not visible; verify screenshot type manually.");
    for(let i=1;i<lines.length;i++){
      const l=lines[i];if(l.y<=(header?.y??-1))continue;
      const rank=l.words.find(w=>/^[RР][1-5]$/iu.test(w.text));
      if(!rank)continue;
      const prev=lines.slice(0,i).reverse().find(n=>n.words.some(w=>w.x>=rank.x-rank.height&&w.x<=rank.x+rank.height*2&&!/^[RР][1-5]$/iu.test(w.text)&&numberFrom(w.text)===undefined));
      if(!prev)continue;
      if(prev.y<=(header?.y??-1)||l.y-prev.y>Math.max(l.height,prev.height)*3.5)continue;
      // A complete row needs the rank and its numeric right-hand column.
      const numeric=lines.filter(n=>Math.abs(n.y-(prev.y+l.y)/2)<=Math.max(l.height,prev.height)*1.2).flatMap(n=>n.words).find(w=>w.x>rank.x+rank.height*6&&numberFrom(w.text)!==undefined);
      if(!numeric){warnings.push("Registration row has no readable right-hand value.");continue}
      const name=prev.words.filter(w=>w.x>=rank.x-rank.height&&w.right<numeric.x).map(w=>w.text).join(" ").trim();
      if(name&&!/^[RР][1-5]$/iu.test(name))rows.push({nickname:name,source});
      else warnings.push("Cannot associate registration rank with a nickname.");
    }
  }
  if(eventType==="alliance_mobilization"){
    // Missions ratios are the row anchors. Use local horizontal regions rather than
    // global line order, because the three podium cards share the same baseline.
    const ratioPattern=/(?:Missions|Задания|Миссии|Задачи)\s*:\s*(\d+)\s*\/\s*(\d+)/iu;
    const heading=lines.find(l=>/(?:Personal Points|Личные очки|Персональные очки)/iu.test(lineText(l))&&/(?:Ranking|Рейтинг|Место)/iu.test(lineText(l)));
    const all=lines.flatMap(l=>l.words);
    const nameAt=(anchor:Word, left:number,right:number)=>{
      const above=lines.filter(l=>l.y<anchor.y&&anchor.y-l.y<=anchor.height*3.5).reverse();
      for(const line of above){
        const text=line.words.filter(w=>w.x>=left&&w.right<=right).map(w=>w.text).join(" ").trim();
        if(/^\s*\[[^\]]+\]\s*\S/u.test(text))return text.replace(/^\s*\[[^\]]+\]\s*/,"");
      }
      return "";
    };
    for(const line of lines){
      // Join adjacent OCR words within each row/card, stopping after the ratio.
      for(let i=0;i<line.words.length;i++){
        const anchor=line.words[i];
        if(!/^(?:Missions|Задания|Миссии|Задачи)/iu.test(anchor.text))continue;
        let value="",end=i;
        for(;end<Math.min(i+8,line.words.length);end++){
          if(end>i&&/^(?:Missions|Задания|Миссии|Задачи)/iu.test(line.words[end].text))break;
          value+=(value?" ":"")+line.words[end].text;
          if(ratioPattern.test(value))break;
        }
        const match=value.match(ratioPattern);
        if(!match){warnings.push("Unreadable missions ratio: "+value);continue}
        const completed=Number(match[1]),total=Number(match[2]);
        if(!Number.isSafeInteger(completed)||!Number.isSafeInteger(total)||completed>total){warnings.push("Invalid missions ratio: "+value);continue}
        const podium=heading?anchor.y<heading.y: false;
        const peers=line.words.filter(w=>/^(?:Missions|Задания|Миссии|Задачи)/iu.test(w.text));
        const index=peers.indexOf(anchor);
        const left=podium?(index>0?(peers[index-1].x+anchor.x)/2:anchor.x-anchor.height*2):anchor.x-anchor.height;
        const right=podium?(index<peers.length-1?(anchor.x+peers[index+1].x)/2+anchor.height*2:anchor.x+anchor.height*12):anchor.x+anchor.height*20;
        const name=nameAt(anchor,left,right);
        const scoreCandidates=all.filter(w=>{
          if(numberFrom(w.text)===undefined||line.words.slice(i,end+1).includes(w))return false;
          return podium?w.y>anchor.y&&w.y-anchor.y<=anchor.height*3&&w.x>=left&&w.right<=right:
            w.x>anchor.x+anchor.height*8&&Math.abs(w.y-anchor.y)<=anchor.height*2;
        });
        if(!name||scoreCandidates.length!==1){warnings.push("Cannot associate missions and points: "+value);continue}
        rows.push({nickname:name,completed,total,points:numberFrom(scoreCandidates[0].text)!,source});
      }
    }
  }
  if(!rows.length)warnings.push("No complete player rows recognized. Check the screenshot and raw text.");
  return {rows,warnings};
}
