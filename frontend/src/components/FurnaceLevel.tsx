import { useState } from "react";
import { formatFurnaceLevel } from "../lib/format";
import fc1 from "whiteout-survival-data/images/fire-crystal/fc-1.png";
import fc2 from "whiteout-survival-data/images/fire-crystal/fc-2.png";
import fc3 from "whiteout-survival-data/images/fire-crystal/fc-3.png";
import fc4 from "whiteout-survival-data/images/fire-crystal/fc-4.png";
import fc5 from "whiteout-survival-data/images/fire-crystal/fc-5.png";
import fc6 from "whiteout-survival-data/images/fire-crystal/fc-6.png";
import fc7 from "whiteout-survival-data/images/fire-crystal/fc-7.png";
import fc8 from "whiteout-survival-data/images/fire-crystal/fc-8.png";
import fc9 from "whiteout-survival-data/images/fire-crystal/fc-9.png";
import fc10 from "whiteout-survival-data/images/fire-crystal/fc-10.png";

const icons=[fc1,fc2,fc3,fc4,fc5,fc6,fc7,fc8,fc9,fc10];
// Same provider encoding as formatFurnaceLevel; sublevels retain their base FC artwork.
export function furnaceIconUrl(level?:number|null):string|undefined {
  if(level==null||!Number.isInteger(level)||level<35||level>80)return;
  return icons[Math.floor((level-30)/5)-1];
}
export function FurnaceLevel({level}:{level?:number|null}){
  const url=furnaceIconUrl(level);
  const [failed,setFailed]=useState<string>();
  return <span className="furnace-level">{url&&failed!==url&&<img src={url} alt="" aria-hidden="true" width={24} height={24} onError={()=>setFailed(url)}/>}<span>{formatFurnaceLevel(level)}</span></span>;
}
