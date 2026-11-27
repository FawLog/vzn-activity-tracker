import { expect,it } from "vitest";
import { matchPlayer, rankedPlayers } from "./ocrMatching";
const p=(fid:string,nickname:string)=>({fid,nickname});
it("suggests whitespace and ornamental unicode variations",()=>{
 expect(matchPlayer("Bogdan_87",[p("1","Bogdan 87")])).toEqual({fid:"1",match:"suggested"});
 expect(matchPlayer("Sora # 29.07",[p("1","Sora #2 ʕ•ᴥ•ʔ"),p("2","Ultron")]).match).toBe("suggested");
 expect(rankedPlayers("Sora # 29.07",[p("2","Ultron"),p("1","Sora #2 ʕ•ᴥ•ʔ")])[0].fid).toBe("1");
 expect(matchPlayer("Emilie R",[p("1","EmilieR")])).toEqual({fid:"1",match:"suggested"});
});
it("does not guess collisions or short names",()=>{
 expect(matchPlayer("M R",[p("1","M&R"),p("2","MR")]).fid).toBe("");
 expect(matchPlayer("Fox",[p("1","Fox"),p("2","Fox")]).fid).toBe("");
 expect(matchPlayer("Ultron",[p("1","Ultron")]).match).toBe("exact");
});

it("suggests observed OCR variations without silently confirming",()=>{
 for(const [ocr,name] of [["Piro e","꧁ Piro ꧂"],["DarksideAMK","Darksideᴬᴹᴷ"],["M & R","M&R"],["CHALS","༄CHALSシ"],["Basel","Basel梦"],["Sora # 29.07","Sora #2 ʕ•ᴥ•ʔ"]]){
 expect(matchPlayer(ocr,[p("1",name),p("2","Ultron")]),ocr+" → "+name).toEqual({fid:"1",match:"suggested"});
 }
 expect(matchPlayer("Piro e",[p("1","Piro"),p("2","Pirox")]).match).toBe("unknown");
});

it("keeps competing decorated prefixes unresolved",()=>{
 expect(matchPlayer("Sora # 29.07",[p("1","Sora #2 ʕ•ᴥ•ʔ"),p("2","Sora #29")]).match).toBe("unknown");
});

it("suggests historical aliases but never silently chooses reused names",()=>{
 expect(matchPlayer("Old Name",[{fid:"1",nickname:"New Name",nickname_aliases:["Old Name"]}])).toEqual({fid:"1",match:"suggested"});
 expect(matchPlayer("Old Name",[{fid:"1",nickname:"New Name",nickname_aliases:["Old Name"]},p("2","Old Name")]).match).toBe("unknown");
});
