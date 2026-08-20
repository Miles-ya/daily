document.addEventListener('DOMContentLoaded',()=>{
  const topic=document.querySelector('#topic-filter');
  const importance=document.querySelector('#importance-filter');
  const cards=[...document.querySelectorAll('.policy-card')];
  const empty=document.querySelector('#filter-empty');
  const apply=()=>{
    let visible=0;
    cards.forEach(card=>{
      const show=(!topic?.value||card.dataset.topics.split(',').includes(topic.value))&&(!importance?.value||card.dataset.importance===importance.value);
      card.hidden=!show;
      if(show)visible+=1;
    });
    if(empty)empty.hidden=visible!==0;
  };
  topic?.addEventListener('change',apply);
  importance?.addEventListener('change',apply);
});
