"""Actual production recipient-button activation, observed without DOM edits."""


def validate_activation(receipt):
    if (not isinstance(receipt, dict) or receipt.get("same_button") is not True
            or receipt.get("connected") is not True or receipt.get("disabled") is not False
            or receipt.get("visible_menu_count") != 1 or receipt.get("menu_items", 0) < 1):
        raise RuntimeError("Recipient button or visible production menu was not independently observed")
    clicks = receipt.get("clicks")
    if (not isinstance(clicks, list) or len(clicks) != 1 or clicks[0].get("trusted") is not True
            or clicks[0].get("same_current_target") is not True):
        raise RuntimeError("Recipient scene did not receive one trusted click on the retained actual button")
    return receipt


def open_recipients(page):
    button = page.locator("#composer .bar button.chip-btn")
    if button.count() != 1:
        raise RuntimeError("No unique mounted production recipient button")
    button.evaluate("""el => {
      const box = el.getBoundingClientRect();
      const state = {button: el, clicks: [], before: {x:box.x,y:box.y,width:box.width,height:box.height}};
      state.listener = event => state.clicks.push({trusted:event.isTrusted,
        same_current_target:event.currentTarget===el, x:event.clientX, y:event.clientY});
      el.addEventListener('click', state.listener);
      window.__relicRecipientActivation = state;
    }""")
    try:
        # Playwright sends pointer input to the production button. No synthetic
        # DOM click, direct menu call, selection assignment or markup is used.
        button.click()
        page.locator("body > .menu").wait_for(state="visible")
        measured = button.evaluate("""el => {
          const state = window.__relicRecipientActivation;
          const menus = Array.from(document.querySelectorAll('body > .menu')).filter(menu => {
            const style=getComputedStyle(menu), box=menu.getBoundingClientRect();
            return style.display!=='none' && style.visibility!=='hidden' && Number(style.opacity)>0 && box.width>0 && box.height>0;
          });
          const rect = element => { const b=element.getBoundingClientRect(); return {x:b.x,y:b.y,width:b.width,height:b.height}; };
          return {source:'actual mounted recipient button and trusted pointer click',
            same_button:state.button===el, connected:el.isConnected, disabled:el.disabled,
            before:state.before, after:rect(el), clicks:state.clicks,
            visible_menu_count:menus.length,
            menu_items:menus.length===1?menus[0].querySelectorAll('button.item').length:0,
            menu_bounds:menus.length===1?rect(menus[0]):null,
            menu_rows:menus.length===1?Array.from(menus[0].querySelectorAll('button.item')).map(item=>({text:item.innerText,bounds:rect(item)})):[]};
        }""")
        return validate_activation(measured)
    finally:
        button.evaluate("""el => {
          const state=window.__relicRecipientActivation;
          if(state) state.button.removeEventListener('click',state.listener);
          delete window.__relicRecipientActivation;
        }""")
