function settingsAiModelEntries(models) {
  if (!models || typeof models !== "object" || Array.isArray(models)) return [];
  return Object.entries(models);
}

function settingsAiModelHasAvailableData(data) {
  return Boolean(data?.available && typeof data.available === "object" && !Array.isArray(data.available));
}

function settingsAiModelFlatOptions(data) {
  return settingsAiModelEntries(data?.available);
}

function settingsAiModelGroupedOptions(data) {
  if (!data?.grouped || typeof data.grouped !== "object" || Array.isArray(data.grouped)) return [];
  return Object.values(data.grouped)
    .filter((group) => group && typeof group === "object")
    .map((group) => ({
      label: String(group.label || ""),
      options: settingsAiModelEntries(group.models),
    }));
}

function settingsAiModelDescriptionText(data) {
  const name = data?.current_name || data?.current || "";
  return `Aktiv: ${name}`;
}

function settingsRenderAiModelSelection(data, select, desc) {
  if (!select || !settingsAiModelHasAvailableData(data)) return false;
  select.innerHTML = "";
  if (data.grouped) {
    settingsAiModelGroupedOptions(data).forEach((group) => {
      const optgroup = document.createElement("optgroup");
      optgroup.label = group.label;
      group.options.forEach(([id, name]) => {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = name;
        if (id === data.current) opt.selected = true;
        optgroup.appendChild(opt);
      });
      select.appendChild(optgroup);
    });
  } else {
    settingsAiModelFlatOptions(data).forEach(([id, name]) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = name;
      if (id === data.current) opt.selected = true;
      select.appendChild(opt);
    });
  }
  if (desc) desc.textContent = settingsAiModelDescriptionText(data);
  return true;
}
