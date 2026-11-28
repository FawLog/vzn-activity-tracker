import {describe,it,expect} from "vitest";
import {cycleDraft} from "./calendar-cycles";
describe("reviewed event cycle draft",()=>{
  it("keeps Canyon battle time unknown and all dates estimated",()=>{
    const rows=cycleDraft("canyon","2028-01-03","4284","a");
    expect(rows.map(p=>p.starts_at)).toEqual(["2028-01-03","2028-01-05","2028-01-07","2028-01-08"]);
    expect(rows[3].ends_at).toBeNull();
    expect(rows.every(p=>p.precision==="date"&&p.confidence==="estimated")).toBe(true);
  });
  it("uses extended SvS preparation and separate battle",()=>{
    const rows=cycleDraft("svs","2028-01-03","4284","a");
    expect(rows[0].ends_at).toBe("2028-01-08T10:00Z");
    expect(rows[1].starts_at).toBe(rows[0].ends_at);
    expect(rows[1].alliance_id).toBeNull();
  });
  it("rejects a non-Monday anchor",()=>expect(()=>cycleDraft("svs","2028-01-04","4284",null)).toThrow());
});
