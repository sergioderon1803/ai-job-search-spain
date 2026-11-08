const fieldLabels = {
  Name: 'Nombre', Location: 'Ubicación', Phone: 'Teléfono', Email: 'Correo electrónico',
  LinkedIn: 'LinkedIn', GitHub: 'GitHub', Status: 'Situación actual', Constraints: 'Preferencias y límites',
  'Driving licence': 'Permiso de conducir', Language: 'Idioma', Level: 'Nivel', Notes: 'Notas',
  Degree: 'Titulación', Period: 'Periodo', Institution: 'Centro', Languages: 'Lenguajes',
  'Frameworks and APIs': 'Frameworks y APIs', 'AI and documents': 'IA y documentos',
  'Data and infrastructure': 'Datos e infraestructura', 'Other skills listed in CV': 'Otras habilidades'
};

function renderProfile() {
  const root = $('#profileSections');
  root.replaceChildren();
  if (!state.profile_sections.length) {
    root.append(element('p', 'Aún no hay secciones disponibles en el perfil.', 'muted'));
    return;
  }
  state.profile_sections.forEach((section, index) => {
    const box = element('article', undefined, 'profile-section');
    const head = element('div', undefined, 'profile-head');
    const title = element('h3', sectionLabels[section.title] || section.title);
    const edit = element('button', 'Editar datos');
    const body = element('div', undefined, 'profile-content');
    renderMarkdown(body, section.content);
    head.append(title, edit);
    box.append(head, body);
    root.append(box);
    edit.onclick = () => {
      if (profileEditing) return;
      profileEditing = true;
      document.querySelectorAll('.profile-head button').forEach(b => { b.disabled = true; });
      body.replaceChildren();
      body.classList.add('profile-edit');
      const form = element('form');
      const grid = element('div', undefined, 'profile-form-grid');
      let previousGroup = '';
      for (const field of section.fields) {
        if (field.group && field.group !== previousGroup) {
          const group = element('h4', field.group, 'profile-form-group');
          grid.append(group);
          previousGroup = field.group;
        } else if (!field.group) previousGroup = '';
        const label = element('label', fieldLabels[field.label] || field.label);
        const input = element('input');
        input.type = 'text';
        input.name = field.id;
        input.value = field.value;
        label.append(input);
        if (field.kind === 'bullet' || field.kind === 'heading' || field.kind === 'text') label.className = 'wide-field';
        grid.append(label);
      }
      if (!section.fields.length) grid.append(element('p', 'Esta sección no contiene campos que se puedan editar.', 'muted'));
      const error = element('p', '', 'error');
      error.setAttribute('role', 'alert');
      const actions = element('div', undefined, 'dialog-actions');
      const save = element('button', 'Guardar cambios', 'primary');
      save.type = 'submit';
      save.disabled = !section.fields.length;
      const cancel = element('button', 'Cancelar');
      cancel.type = 'button';
      actions.append(save, cancel);
      form.append(grid, error, actions);
      body.append(form);
      cancel.onclick = () => { profileEditing = false; renderProfile(); };
      form.onsubmit = async event => {
        event.preventDefault();
        save.disabled = true;
        try {
          const response = await fetch('/api/profile', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-Dashboard-Token': state.token},
            body: JSON.stringify({index, values: Object.fromEntries(new FormData(form)), version: state.profile_version})
          });
          const result = await response.json();
          if (!response.ok) throw Error(result.error);
          profileEditing = false;
          await load();
        } catch (err) {
          error.textContent = err.message;
          save.disabled = false;
        }
      };
      form.querySelector('input')?.focus();
    };
  });
}
