import {fireEvent,render} from "@testing-library/react";
import {describe,it,expect} from "vitest";
import {FurnaceLevel,furnaceIconUrl} from "./FurnaceLevel";
describe("FurnaceLevel",()=>{
 it.each([[35,1],[39,1],[55,5],[59,5],[80,10]])("maps provider level %i to FC%i",(level,fc)=>expect(furnaceIconUrl(level)).toContain("fc-"+fc+".png"));
 it.each([null,undefined,0,30,34,81,35.5])("does not invent a badge for %s",level=>expect(furnaceIconUrl(level)).toBeUndefined());
 it("keeps the exact textual level if artwork fails",()=>{const {container,getByText}=render(<FurnaceLevel level={56}/>);expect(getByText("FC5-1")).toBeTruthy();fireEvent.error(container.querySelector("img")!);expect(container.querySelector("img")).toBeNull();expect(getByText("FC5-1")).toBeTruthy()});
});
