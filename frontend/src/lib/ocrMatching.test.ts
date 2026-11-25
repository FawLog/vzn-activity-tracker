import { expect,it } from "vitest";
import { matchPlayer, rankedPlayers } from "./ocrMatching";
const p=(fid:string,nickname:string)=>({fid,nickname});
it("suggests whitespace and ornamental unicode variations",()=>{
 expect(matchPlayer("Bogdan_87",[p("1","Bogdan 87")])).toEqual({fid:"1",match:"suggested"});
 expect(matchPlayer("Sora # 29.07",[p("1","Sora #2 ʕ•ᴥ•ʔ"),p("2","Ultron")]).match).toBe("unknown");
 expect(rankedPlayers("Sora # 29.07",[p("2","Ultron"),p("1","Sora #2 ʕ•ᴥ•ʔ")])[0].fid).toBe("1");
 expect(matchPlayer("Emilie R",[p("1","EmilieR")])).toEqual({fid:"1",match:"suggested"});
});
it("does not guess collisions or short names",()=>{
 expect(matchPlayer("M R",[p("1","M&R"),p("2","MR")]).fid).toBe("");
 expect(matchPlayer("Fox",[p("1","Fox"),p("2","Fox")]).fid).toBe("");
 expect(matchPlayer("Ultron",[p("1","Ultron")]).match).toBe("exact");
});
