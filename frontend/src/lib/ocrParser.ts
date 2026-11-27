import type { OcrPreview } from "./api";

export type ParsedRow = { nickname: string; damage?: number; completed?: number; total?: number; points?: number; role?: "main"|"substitute"; rank?: number; source: string };
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
export type FoundryImportInfo = {main_count?:number;substitute_count?:number;outcome?:"victory"|"defeat";own_score?:number;opponent_score?:number;opponent_state?:string;opponent_tag?:string;opponent_name?:string};
type ParsedScreenshot = {rows:ParsedRow[];warnings:string[];foundry?:FoundryImportInfo};
function numericRuns(line:Line):Array<Word & {value:number}> {
  const groups:Word[]=[];
  for(const w of line.words){
    if(!/^[\d, \u00a0\u202f]+$/u.test(w.text))continue;
    const prev=groups[groups.length-1];
    if(prev&&w.x-prev.right<=Math.max(prev.height,w.height)*.55&&w.x>=prev.x){
      prev.text+=w.text;prev.right=w.right;
    }else groups.push({...w});
  }
  return groups.flatMap(w=>{const value=numberFrom(w.text);return value===undefined?[]:[{...w,value}]});
}
// The in-game combatant dialog repeats the legion and count headers on every
// page. Its per-row Join/Substitute label is the role anchor, not R1–R5
// (those are group headings). Never interpret voting or troop power as points.
const registrationMode=(mode:string)=>mode==="foundry_registration"||mode==="canyon_registration";
const powerHeading=(line:Line,mode:string)=>/\bTroop\s+Power\b/iu.test(lineText(line))||mode==="canyon_registration"&&/^Power$/iu.test(line.words[0]?.text??"");
function foundryCombatantList(lines:Line[],heading:Line,mode:string,sessionKey:string,source:string):ParsedScreenshot {
  const rows:ParsedRow[]=[],warnings:string[]=[],foundry:FoundryImportInfo={};
  if(!registrationMode(mode))return {rows,warnings:["In-game combatant list is registration evidence, not battle results."]};
  const legion=lineText(heading).match(/\bLegion\s*([12])\s+Combatants\b/iu)?.[1];
  if(!legion||sessionKey!=="legion_"+legion)return {rows,warnings:["Combatant list belongs to a different legion. Remove this screenshot."]};
  const troop=lines.find(l=>l.y>heading.y&&powerHeading(l,mode));
  const footer=lines.find(l=>l.y>(troop?.y??heading.y)&&/\bParticipants\s+only\b/iu.test(lineText(l)));
  if(!troop||!footer)return {rows,warnings:["Incomplete combatant dialog header/footer; use an uncropped screenshot."]};
  const headerWords=lines.filter(l=>l.y>heading.y&&l.y<troop.y).flatMap(l=>l.words);
  const join=headerWords.find(w=>/^Join$/iu.test(w.text));
  const sub=headerWords.find(w=>/^Substitute$/iu.test(w.text));
  if(!join||!sub||join.x>=sub.x)return {rows,warnings:["Cannot locate both combatant count columns. Review this screenshot."]};
  const middle=(join.x+sub.x)/2;
  const maxX=Math.max(sub.right,...lines.filter(l=>l.y>=heading.y&&l.y<=footer.y).flatMap(l=>l.words.map(w=>w.right)));
  const readCount=(right:boolean,capacity:number,label:Word)=>{
    const matches=lines.filter(l=>l.y>=label.y-label.height*.6&&l.y<troop.y).flatMap(l=>{
      const words=l.words.filter(w=>(w.x>=middle)===right);
      const text=words.map(w=>w.text).join("").replace(/\s/g,"");
      return [...text.matchAll(/(\d{1,2})\/(\d{1,2})(?!\d)/g)].filter(m=>Number(m[2])===capacity&&Number(m[1])<=capacity).map(m=>Number(m[1]));
    });
    const unique=[...new Set(matches)];
    return unique.length===1?unique[0]:undefined;
  };
  foundry.main_count=readCount(false,30,join);
  foundry.substitute_count=readCount(true,10,sub);
  if(foundry.main_count===undefined||foundry.substitute_count===undefined)
    warnings.push("Unreadable Join/Substitute counts; verify against the in-game header.");
  const area=lines.filter(l=>l.y>troop.y+troop.height*.6&&l.y<footer.y-footer.height*.6);
  const anchors=area.flatMap(l=>l.words).filter(w=>/^(Join|Substitute)$/iu.test(w.text)&&w.x>maxX*.62).sort((a,b)=>a.y-b.y);
  for(let i=0;i<anchors.length;i++){
    const anchor=anchors[i],prev=anchors[i-1],next=anchors[i+1];
    const top=Math.max(troop.y+troop.height*.6,prev?(prev.y+anchor.y)/2:-Infinity,anchor.y-anchor.height*3.2);
    const bottom=Math.min(footer.y-footer.height*.6,next?(anchor.y+next.y)/2:Infinity,anchor.y+anchor.height*3.2);
    const region=area.filter(l=>l.y>top&&l.y<bottom);
    const powers=region.flatMap(numericRuns).filter(w=>w.x>maxX*.19&&w.x<maxX*.51&&w.right<anchor.x&&w.y>=anchor.y-anchor.height*.65&&w.y-anchor.y<=Math.max(w.height,anchor.height)*2.8);
    // Troop power is optional registration evidence, not an eligibility gate.
    // Use its baseline when reliable; otherwise use the role label and the
    // fixed nickname column. Stay inside this card's midpoint boundaries.
    const power=powers.length===1?powers[0]:undefined;
    const nameLeft=power?Math.max(maxX*.20,power.x-power.height*2.35):maxX*.20;
    const nameRight=power?power.x+power.height*2.35:maxX*.40;
    const names=region.filter(l=>power
      ?l.y<power.y-power.height*.55&&power.y-l.y<=Math.max(l.height,power.height)*3.2
      :l.y>=anchor.y-Math.max(l.height,anchor.height)*2.1&&l.y<=anchor.y+anchor.height*.35
    ).map(l=>{
      const words=l.words.filter(w=>w.x>=nameLeft&&w.right<Math.min(anchor.x-anchor.height*.5,maxX*.78));
      const first=words[0],name=words.map(w=>w.text).join(" ").trim();
      return {first,name,l};
    }).filter(v=>v.first&&v.first.x<=nameRight&&/[\p{L}\p{N}]/u.test(v.name)&&numberFrom(v.name)===undefined&&!/^(?:R[0-5]\b|Rank\s+[0-5]\b|Voted\b|Troop\s+Power\b|Participants\s+only\b)/iu.test(v.name)&&!(/^[\d\s,./]+$/u.test(v.name)));
    const distinct=[...new Set(names.map(v=>v.name))];
    if(distinct.length!==1){warnings.push("Skipped incomplete combatant row near y="+Math.round(anchor.y)+": missing or ambiguous nickname.");continue}
    rows.push({nickname:distinct[0],role:/^Join$/iu.test(anchor.text)?"main":"substitute",source});
  }
  if(!anchors.length)warnings.push("No per-player Join/Substitute labels recognized.");
  warnings.push("In-game combatant list: "+rows.length+" of "+anchors.length+" role anchors read. Verify the final roster and both role counts.");
  return {rows,warnings,foundry};
}

function foundryScreenshot(lines:Line[],mode:string,sessionKey:string,source:string):ParsedScreenshot {
  const combatantHeading=lines.find(l=>/\bLegion\s*[12]\s+Combatants\b/iu.test(lineText(l)));
  if(combatantHeading)return foundryCombatantList(lines,combatantHeading,mode,sessionKey,source);
  // A damaged dialog heading should not fall through to the mail parser.
  if(lines.some(l=>/\bParticipants\s+only\b/iu.test(lineText(l)))&&lines.some(l=>powerHeading(l,mode)))
    return {rows:[],warnings:["Cannot verify the in-game combatant list legion. Use a screenshot with the full heading."]};
  const rows:ParsedRow[]=[],warnings:string[]=[],foundry:FoundryImportInfo={};
  const all=lines.flatMap(l=>l.words);
  const maxX=Math.max(1,...all.map(w=>w.right));
  const mailText=lines.map(lineText).join(" ");
  if(registrationMode(mode)&&((mode==="foundry_registration"&&/\bCanyon\s+Clash\b/iu.test(mailText))||(mode==="canyon_registration"&&/\bFoundry\s+Battle\b/iu.test(mailText))))return {rows,warnings:["Mail belongs to a different event. Remove this screenshot."]};
  const legion=mailText.match(/\bLegion\s*([12])\b/iu)?.[1];
  if(legion&&sessionKey!=="legion_"+legion)return {rows,warnings:["Mail belongs to a different legion. Remove this screenshot."]};
  const personal=lines.find(l=>/Personal\s+Arsenal\s+Points/iu.test(lineText(l)));
  const section=/\b(Combatants|Substitutes)\s*:\s*(\d+)\s*\/\s*(\d+)/iu;
  const headers=lines.flatMap(l=>{const m=lineText(l).match(section);if(!m)return [];const role=m[1].toLowerCase()==="combatants"?"main" as const:"substitute" as const;const n=Number(m[2]);if(n<0||n>(role==="main"?30:10))return [];if(role==="main")foundry.main_count=n;else foundry.substitute_count=n;return [{y:l.y,role}];});
  if(registrationMode(mode)){
    if(personal||/\b(?:Legion Tally|Personal Arsenal Points|DEFEAT!|VICTORY!)\b/iu.test(mailText))return {rows,warnings:["Battle result mail is not a registration list."]};
    const ranks=all.filter(w=>/^[RР]\s*[0-5]$/iu.test(w.text)&&w.x<maxX*.5).sort((a,b)=>a.y-b.y);
    for(let i=0;i<ranks.length;i++){
      const rank=ranks[i],prev=ranks[i-1],next=ranks[i+1];
      const preceding=headers.filter(h=>h.y<rank.y);
      const header=preceding[preceding.length-1];
      const top=Math.max(header?.y??-Infinity,rank.y-rank.height*4.5,prev?(prev.y+rank.y)/2-rank.height*.5:-Infinity);
      const bottom=Math.min(rank.y+rank.height*.65,next?(rank.y+next.y)/2:Infinity);
      const region=lines.filter(l=>l.y>top&&l.y<=bottom);
      const rightValues=region.flatMap(l=>[...numericRuns(l),...l.words.filter(w=>/^\d+(?:\.\d+)?[KMBT]$/iu.test(w.text))]).filter(w=>w.x>rank.x+rank.height*6);
      const right=rightValues.length===1?rightValues[0].x-rank.height*.35:rank.x+rank.height*14;
      const nameWords=region.flatMap(l=>l.words).filter(w=>w.y<rank.y-rank.height*.4&&w.x>=rank.x-rank.height&&w.right<right&&!/^[RР]\s*[0-5]$/iu.test(w.text));
      const base=nameWords.filter(w=>/[\p{L}\p{N}]/u.test(w.text)).sort((a,b)=>b.height-a.height||a.y-b.y)[0];
      const nickname=base?nameWords.filter(w=>Math.abs(w.y-base.y)<=Math.max(w.height,base.height)*.95).sort((a,b)=>a.x-b.x).map(w=>w.text).join(" ").trim():"";
      if(!nickname||rightValues.length!==1){warnings.push("Incomplete or ambiguous registration row near y="+Math.round(rank.y));continue}
      const role=header?.role??(headers.some(h=>h.role==="substitute"&&h.y>rank.y)?"main":undefined);
      rows.push({nickname,...(role?{role}:{}),source});
    }
    if(!ranks.length)warnings.push("No complete R0–R5 registration rows found.");
    if(rows.some(r=>!r.role))warnings.push("Section header not visible; verify main/substitute role or use overlap matching.");
    return {rows,warnings,foundry};
  }
  if(headers.length||/\bselected as a combatant\b/iu.test(mailText))return {rows,warnings:["Registration mail is not a battle result list."]};
  const outcomeLine=lines.find(l=>/^\s*(VICTORY|DEFEAT)\s*!?\s*$/iu.test(lineText(l)));
  if(outcomeLine){
    foundry.outcome=/VICTORY/iu.test(lineText(outcomeLine))?"victory":"defeat";
    const tally=lines.find(l=>l.y>outcomeLine.y&&/Legion Tally/iu.test(lineText(l)));
    const banner=lines.filter(l=>l.y>=outcomeLine.y-outcomeLine.height*3&&l.y<(tally?.y??outcomeLine.y+outcomeLine.height*12));
    const side=(right:boolean)=>banner.map(l=>({...l,words:l.words.filter(w=>(w.x>=maxX*.5)===right)})).filter(l=>l.words.length);
    const readSide=(right:boolean)=>{
      const ls=side(right);
      const team=ls.find(l=>/\[[^\]]+\]\s*\S/u.test(lineText(l)));
      const m=team&&lineText(team).match(/\[\s*([^\]]+?)\s*\]\s*(.+)$/u);
      const state=ls.map(lineText).join(" ").match(/#\s*(\d{1,6})\b/u)?.[1];
      const scores=team?ls.filter(l=>l.y>team.y).flatMap(numericRuns):[];
      return {tag:m?.[1].replace(/\s+/g,""),name:m?.[2].trim(),state,score:scores.length===1?scores[0].value:undefined};
    };
    const own=readSide(false),opp=readSide(true);
    if(own.tag&&opp.tag){
      foundry.own_score=own.score;foundry.opponent_score=opp.score;
      foundry.opponent_tag=opp.tag;foundry.opponent_name=opp.name;foundry.opponent_state=opp.state;
    }
  }
  if(!personal&&(/Legion Tally|Control Rewards|Gathering Rewards|Loot Rewards|KO Rewards|Sieges by Mercenaries|\bMVP\b/iu.test(mailText)||outcomeLine)){
    return {rows,warnings:["Team summary only; no personal ranking rows imported."],foundry};
  }
  const area=lines.filter(l=>l.y>(personal?.y??-Infinity));
  const rankWords=area.flatMap(l=>l.words).filter(w=>w.x<maxX*.25&&numberFrom(w.text)!==undefined&&numberFrom(w.text)!>=1&&numberFrom(w.text)!<=40);
  if(!personal&&!rankWords.length)return {rows,warnings:["Personal ranking header or rank anchors missing; review this screenshot."],foundry};
  for(const line of area){
    for(const n of numericRuns(line).filter(w=>w.x>=maxX*.25)){
      const above=area.filter(l=>l.y<line.y-n.height*.65&&line.y-l.y<=n.height*4.5).reverse();
      const names=above.map(l=>{
        const words=l.words.filter(w=>w.x>=n.x-n.height*.75&&w.x<maxX&&w.right>n.x-n.height*.25);
        const first=words[0],name=words.map(w=>w.text).join(" ").trim();
        return {l,first,name};
      }).filter(v=>v.first&&Math.abs(v.first.x-n.x)<=n.height*1.1&&/[\p{L}]/u.test(v.name)&&!/(?:Personal Arsenal Points|Legion Tally|MVP|Rewards|Expires at|Mail|Delete)/iu.test(v.name));
      const best=names[0];
      if(!best)continue;
      // A score must be in the nickname column, on its own line. Never use a
      // rank, team total, date, avatar label or the previous player's nickname.
      if(line.words.some(w=>w.x>=n.x-n.height*.4&&w.right>n.right+n.height*.4&&/[\p{L}]/u.test(w.text)))continue;
      const ranks=rankWords.filter(w=>w.y>=best.l.y-n.height&&w.y<=line.y+n.height);
      if(ranks.length>1)continue;
      const rank=ranks.length===1?numberFrom(ranks[0].text):undefined;
      if(rank===undefined&&!personal&&!rankWords.length)continue;
      rows.push({nickname:best.name,points:n.value,...(rank!==undefined?{rank}:{}),source});
    }
  }
  if(!rows.length)warnings.push("No complete personal points rows recognized; verify screenshot.");
  else warnings.push("Personal results: "+rows.length+" rows including "+rows.filter(r=>r.points===0).length+" explicit zeros. Review all matches.");
  return {rows,warnings,foundry};
}
export function parseScreenshot(preview:OcrPreview,eventType:string,sessionKey:string,source:string):ParsedScreenshot {
  const lines=linesFrom(preview), rows:ParsedRow[]=[],warnings:string[]=[];
  if(!lines.length)return {rows,warnings:["No word coordinates; inspect the original screenshot and raw text."]};
  if(registrationMode(eventType)||eventType==="foundry_results")return foundryScreenshot(lines,eventType,sessionKey,source);
  if(eventType==="bear_trap"){
    const heading=lines.find(l=>/(?:Trap\s*[12]\s*Damage\s*Rewards|(?:ловушк[аеиу]|капкан)\s*[12])/iu.test(lineText(l)));
    const trap=heading&&lineText(heading).match(/(?:Trap|ловушк[аеиу]|капкан)\s*([12])/iu)?.[1];
    if(trap&&sessionKey!=="trap_"+trap){if(sessionKey==="trap_1"||sessionKey==="trap_2")return {rows,warnings:["Trap header does not match the selected session."]};warnings.push("Verify host and local trap number: screenshot numbering may differ from group cycle numbering.");}
    if(!trap)warnings.push("Trap number not visible: verify selected session manually.");
    const header=lines.find(l=>l.y>(heading?.y??-1)&&/(?:Ranking|рейтинг|место)/iu.test(lineText(l))&&/(?:Damage\s*Points|урон)/iu.test(lineText(l)));
    if(!header)warnings.push("Ranking header not visible; verify screenshot type manually.");
    // Damage labels are row anchors. OCR may put avatar/rank decorations on
    // their own intervening lines, so the immediately preceding line is not
    // necessarily the nickname. Search within the same bounded row and column.
    const damagePattern=/(?:Damage\s*Points|(?:очки\s+)?урона?)\s*:\s*(.+)$/iu;
    const anchors=lines.filter(l=>l.y>(header?.y??heading?.y??-1)&&damagePattern.test(lineText(l)));
    let positiveAnchors=0;
    for(let i=0;i<anchors.length;i++){
      const l=anchors[i],text=lineText(l),match=text.match(damagePattern)!;
      const damage=numberFrom(match[1]);
      const label=l.words.find(w=>/^(?:Damage|очки|урон)/iu.test(w.text));
      if(damage===0){warnings.push("Skipped zero/unranked row: "+text);continue}
      positiveAnchors++;
      if(damage===undefined||!label){warnings.push("Unreadable damage row: "+text);continue}
      const top=Math.max(header?.y??heading?.y??-1,anchors[i-1]?.y??-1,l.y-l.height*5);
      const region=lines.filter(n=>n.y>top&&n.y<l.y);
      const all=region.flatMap(n=>n.words);
      const nearby=all.filter(w=>w.right<label.x-l.height).map(w=>w.text).join(" ");
      if(/un\s*ran\s*ked|unran\s*ked|без\s*ранга/iu.test(nearby)){warnings.push("Skipped zero/unranked row: "+text);continue}
      const column=(w:Word)=>w.x>=label.x-l.height*1.25&&w.right>=label.x-l.height*.5;
      // Reassemble slightly offset tag/name glyphs around each candidate baseline.
      const candidates=region.map(n=>{
        const words=all.filter(w=>column(w)&&Math.abs(w.y-n.y)<=Math.max(w.height,n.height)*.8)
          .sort((a,b)=>a.x-b.x);
        const raw=words.map(w=>w.text).join(" ").trim();
        const tagged=raw.match(/^\s*\[\s*([^\]]{1,24})\]\s*(.+)$/u);
        const name=(tagged?tagged[2]:raw).trim();
        const first=words[0];
        const plausible=!!first&&Math.abs(first.x-label.x)<=l.height*1.25&&
          /\p{L}/u.test(name)&&!/(?:Damage\s*Points|Damage\s*Ranking|Personal\s*Damage|Rewards|Ranking|урон|рейтинг)/iu.test(name);
        return {name,tagged:!!tagged,plausible,y:n.y};
      }).filter(c=>c.plausible);
      const tagged=candidates.filter(c=>c.tagged);
      const distinct=[...new Set(tagged.map(c=>c.name))];
      // Prefer an explicit alliance tag. Without one, only accept an unambiguous
      // aligned text line; never borrow a nickname from the previous damage row.
      const plain=[...new Set(candidates.filter(c=>!c.tagged).map(c=>c.name))];
      const name=distinct.length===1?distinct[0]:distinct.length===0&&plain.length===1?plain[0]:"";
      if(!name){warnings.push("Cannot associate damage with a nickname: "+text);continue}
      rows.push({nickname:name,damage,source});
    }
    warnings.push("Bear damage rows: "+rows.length+" of "+positiveAnchors+" detected non-zero damage anchors; verify against the screenshot.");
  }else if(eventType==="alliance_championship"){
    const header=lines.find(l=>/(?:Registered|зарегистрирован[оы]?|регистрация)\s*:\s*\d+\s*\/\s*\d+/iu.test(lineText(l)));
    if(!header)warnings.push("Registration header not visible; verify screenshot type manually.");
    const all=lines.flatMap(l=>l.words).filter(w=>w.y>(header?.y??-1));
    // Use each rank's own coordinates, not the baseline of a nearby OCR word.
    // Adjacent rank anchors bound the row, so a missing name cannot borrow its neighbour.
    const isRank=(w:Word)=>/^[RР]\s*[1-5]$/iu.test(w.text);
    const ranks=all.filter(isRank).sort((a,b)=>a.y-b.y);
    for(let i=0;i<ranks.length;i++){
      const rank=ranks[i],previous=ranks[i-1],next=ranks[i+1];
      const top=Math.max(header?.y??-1,rank.y-rank.height*4.5,previous?(previous.y+rank.y)/2-rank.height*.5:-Infinity);
      const bottom=Math.min(rank.y+rank.height*.65,next?(rank.y+next.y)/2:Infinity);
      const region=all.filter(w=>w.y>top&&w.y<=bottom);
      const scores=region.filter(w=>w.x>rank.x+rank.height*6&&numberFrom(w.text)!==undefined);
      const left=rank.x-rank.height*.65;
      const right=scores.length?Math.min(...scores.map(w=>w.x)):rank.x+rank.height*14;
      const nameWords=region.filter(w=>w.y<rank.y-rank.height*.4&&w.x>=left&&w.right<right&&!isRank(w));
      // Preserve offset decorations when they share the same nickname baseline.
      const base=nameWords.filter(w=>/\p{L}|\p{N}/u.test(w.text)).sort((a,b)=>b.height-a.height||a.y-b.y)[0];
      const name=base?nameWords.filter(w=>Math.abs(w.y-base.y)<=Math.max(w.height,base.height)*.95).sort((a,b)=>a.x-b.x).map(w=>w.text).join(" ").trim():"";
      if(!name||scores.length!==1){
        warnings.push("Skipped registration row near y="+Math.round(rank.y)+": "+(name||"(nickname unreadable)")+"; "+(!name?"no nickname":scores.length?"ambiguous right-hand value":"no readable right-hand value")+".");
        continue;
      }
      rows.push({nickname:name,source});
    }
    if(!ranks.length)warnings.push("No registration rank anchors recognized.");
    warnings.push("Registration rows: "+rows.length+" of "+ranks.length+" detected rank anchors; verify against the screenshot.");

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
