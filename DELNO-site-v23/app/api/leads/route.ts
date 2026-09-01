export const runtime = "edge";

type LeadPayload={source?:unknown;name?:unknown;phone?:unknown;email?:unknown;company?:unknown};
const clean=(value:unknown,max=200)=>typeof value==="string"?value.trim().slice(0,max):"";

export async function POST(request:Request){
  const apiBase=(process.env.DELNO_API_URL||process.env.NEXT_PUBLIC_DELNO_API_URL||"").replace(/\/$/,"");
  const tenantSlug=process.env.DELNO_TENANT_SLUG||"delno-demo";

  let input:LeadPayload;
  try{input=await request.json() as LeadPayload}catch{return Response.json({error:"INVALID_JSON"},{status:400})}
  const lead={source:clean(input.source,120),name:clean(input.name,120),phone:clean(input.phone,60),email:clean(input.email,160),company:clean(input.company,160)};
  if(!lead.name||!lead.phone) return Response.json({error:"NAME_AND_PHONE_REQUIRED"},{status:400});

  if(apiBase){
    const response=await fetch(`${apiBase}/v1/public/leads`,{
      method:"POST",
      headers:{"Content-Type":"application/json","X-Tenant-Slug":tenantSlug},
      body:JSON.stringify({...lead,source:lead.source||"Сайт DELNO"}),
    });
    if(response.ok) return Response.json({ok:true});
    const detail=await response.text().catch(()=> "");
    return Response.json({error:"DELNO_API_LEAD_FAILED",detail:detail.slice(0,500)},{status:502});
  }

  const webhook=process.env.LEAD_WEBHOOK_URL;
  const telegramToken=process.env.TELEGRAM_BOT_TOKEN;
  const telegramChatId=process.env.TELEGRAM_CHAT_ID;
  if(!webhook&&(!telegramToken||!telegramChatId)) return Response.json({error:"LEAD_STORAGE_NOT_CONFIGURED"},{status:503});
  const payload={...lead,created_at:new Date().toISOString()};
  const telegramText=["Новая заявка DELNO",`Источник: ${lead.source||"Сайт"}`,`Имя: ${lead.name}`,`Телефон: ${lead.phone}`,lead.company?`Компания: ${lead.company}`:"",lead.email?`Почта: ${lead.email}`:""].filter(Boolean).join("\n");
  const response=webhook
    ?await fetch(webhook,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})
    :await fetch(`https://api.telegram.org/bot${telegramToken}/sendMessage`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({chat_id:telegramChatId,text:telegramText})});
  if(!response.ok) return Response.json({error:"LEAD_DELIVERY_FAILED"},{status:502});
  return Response.json({ok:true});
}
