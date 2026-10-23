/* Opportunity OS Autofill Companion.
   This runs only after a user clicks the popup button on the active tab.
   No credential collection, tracking, external network, or form submission. */
"use strict";
const $=id=>document.getElementById(id);
const storageKey="opportunity_os_autofill_pack_v1";
let pack=null;
function show(message){$("status").textContent=message;}
function packValid(value){
  return value && value.format==="opportunity-os-autofill-pack-v1" &&
    value.contact && typeof value.contact==="object" &&
    value.education && typeof value.education==="object" &&
    value.links && typeof value.links==="object" &&
    value.application && typeof value.application.official_url==="string" &&
    /^https:\/\//i.test(value.application.official_url);
}
async function loadSaved(){
  const v=await chrome.storage.local.get(storageKey);
  if(packValid(v[storageKey])){
    pack=v[storageKey];
    $("loaded").textContent="Ready for: "+String(pack.application.company||"Employer")+" — "+String(pack.application.title||"job");
    show("Application pack loaded. Open the official job form, then choose Fill.");
  }
}
$("pack").addEventListener("change",async event=>{
  const file=event.target.files?.[0];
  if(!file)return;
  if(file.size>150000 || !file.name.toLowerCase().endsWith(".json")){show("Select a valid Opportunity OS JSON pack under 150 KB.");return;}
  try{
    const value=JSON.parse(await file.text());
    if(!packValid(value))throw Error("Unrecognized pack format. Export from Opportunity OS.");
    await chrome.storage.local.set({[storageKey]:value});
    pack=value;
    $("loaded").textContent="Ready for: "+value.application.company+" — "+value.application.title;
    show("Pack saved locally. No application was submitted.");
  }catch(error){show("Import failed: "+error.message);}
});
$("clear").addEventListener("click",async()=>{
  await chrome.storage.local.remove(storageKey);
  pack=null;$("loaded").textContent="No application pack saved.";
  $("resume").value="";$("pack").value="";
  show("Saved profile cleared from this browser extension.");
});
$("open").addEventListener("click",async()=>{
  if(!pack){show("Import your application pack first.");return;}
  const url=pack.application.official_url;
  try{
    const parsed=new URL(url);
    if(parsed.protocol!=="https:" || parsed.username || parsed.password)throw Error("Unsafe application link");
    await chrome.tabs.create({url:parsed.href});
    show("Official job page opened. Navigate to its form and choose Fill.");
  }catch(error){show("Unable to open listing: "+error.message);}
});
$("fill").addEventListener("click",async()=>{
  if(!pack){show("Import an application pack first.");return;}
  const button=$("fill");button.disabled=true;
  try{
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!tab || !/^https?:\/\//i.test(tab.url||""))throw Error("Open a supported HTTPS employer application page.");
    let pdf=null;
    const file=$("resume").files?.[0];
    if(file){
      if(file.size>3_000_000 || !file.name.toLowerCase().endsWith(".pdf"))throw Error("Choose the original PDF under 3 MB.");
      const bytes=new Uint8Array(await file.arrayBuffer());
      if(bytes.length<5 || String.fromCharCode(...bytes.slice(0,5))!=="%PDF-")throw Error("Invalid PDF header.");
      pdf={name:file.name,bytes:Array.from(bytes)};
    }
    const output=await chrome.scripting.executeScript({
      target:{tabId:tab.id},func:fillSupportedForm,args:[pack,pdf]
    });
    const value=output?.[0]?.result;
    if(!value)throw Error("This form may be blocked or inside a protected iframe.");
    show("Prepared: "+value.filled+" text fields; "+value.resume+" resume attachments.\n"+
       (value.skipped?"Skipped "+value.skipped+" existing/unsupported fields.\n":"")+
       "Review every answer and submit on the employer site. Nothing was sent by this extension.");
  }catch(error){show("Autofill did not finish: "+error.message);}
  finally{button.disabled=false;}
});
loadSaved().catch(error=>show("Unable to access local extension storage: "+error.message));

/* Injected function: self-contained because executeScript serializes its source.
   Does not click any button, auto-submit, navigate, or answer legal/EEO fields. */
function fillSupportedForm(data,pdf){
  const contact=data.contact||{},edu=data.education||{},links=data.links||{};
  let filled=0,resume=0,skipped=0;
  const ignored=/password|birth|dob|gender|race|ethnic|disabil|veteran|citizenship|nationality|visa|sponsor|work.authorization|right.to.work|salary|compensation|expectation|notice.period|ssn|social.security|marital|age|pronouns|consent|privacy|agreement|legal|cover.letter|why.do.you|refer|referral|signature|captcha|eligibilit|relocat|gender.identity|sexual.orientation|immigration|background.check|government.id|aadhaar|passport/i;
  const lookup=[
    [/\b(first.name|given.name|firstname|fname)\b/i,contact.first_name],
    [/\b(last.name|family.name|surname|lastname|lname)\b/i,contact.last_name],
    [/\b(full.name|your.name|candidate.name|applicant.name)\b/i,contact.full_name],
    [/\b(e.mail|email|emailaddress)\b/i,contact.email],
    [/\b(phone|mobile|telephone|contact.number)\b/i,contact.phone],
    [/\blinked.?in\b/i,links.linkedin],
    [/\bgithub\b/i,links.github],
    [/\b(portfolio|personal.website|personal.site|website.url|website)\b/i,links.portfolio],
    [/\b(college|university|institution|institute|school.name)\b/i,edu.institution],
    [/\b(degree|qualification|education.level|course.of.study)\b/i,edu.degree],
    [/\b(graduation.year|graduation date|expected.graduation|graduating.year|passing.year|year.of.passing)\b/i,edu.graduation_year],
    [/\b(cgpa|cumulative.gpa|overall.gpa|grade.point.average)\b/i,edu.cgpa],
    [/\b(overall.percentage|aggregate.percentage|percentage.marks)\b/i,edu.percentage],
    [/\b(current.city|city.of.residence|your.city|location.city)\b/i,edu.city],
    [/\b(country.of.residence|your.country|country)\b/i,edu.country]
  ];
  function descriptor(element){
    const pieces=[element.name,element.id,element.getAttribute("aria-label"),element.placeholder,element.autocomplete];
    for(const lab of element.labels||[])pieces.push(lab.textContent);
    const parent=element.closest("label");
    if(parent)pieces.push(parent.textContent);
    return pieces.filter(Boolean).join(" ").replace(/[_-]/g," ").trim();
  }
  const elements=document.querySelectorAll("input,textarea");
  for(const element of elements){
    if(element.disabled||element.readOnly)continue;
    const type=(element.type||"text").toLowerCase(),label=descriptor(element);
    if(ignored.test(label)){skipped++;continue;}
    if(type==="file"){
      if(!pdf || !/\b(resume|cv|curriculum vitae)\b/i.test(label) || element.files?.length){skipped++;continue;}
      try{
        const file=new File([new Uint8Array(pdf.bytes)],pdf.name,{type:"application/pdf"});
        const dt=new DataTransfer();dt.items.add(file);element.files=dt.files;
        element.dispatchEvent(new Event("input",{bubbles:true}));
        element.dispatchEvent(new Event("change",{bubbles:true}));
        resume++;
      }catch(_){skipped++;}
      continue;
    }
    if(!["text","email","tel","url","number","search"].includes(type) &&
       element.tagName.toLowerCase()!=="textarea")continue;
    if(String(element.value||"").trim()){skipped++;continue;}
    const match=lookup.find(([pattern,value])=>value && pattern.test(label));
    if(!match)continue;
    try{
      const text=String(match[1]);
      const setter=Object.getOwnPropertyDescriptor(
        element.tagName.toLowerCase()==="textarea" ? HTMLTextAreaElement.prototype:HTMLInputElement.prototype,
        "value"
      )?.set;
      if(setter)setter.call(element,text);else element.value=text;
      element.dispatchEvent(new Event("input",{bubbles:true}));
      element.dispatchEvent(new Event("change",{bubbles:true}));
      filled++;
    }catch(_){skipped++;}
  }
  return {filled,resume,skipped};
}
