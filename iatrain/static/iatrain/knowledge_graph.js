(function () {
  "use strict";

  var app = document.getElementById("knowledge-graph-app");
  if (!app) return;

  var canvas = document.getElementById("kg-canvas");
  var context = canvas.getContext("2d");
  var stage = document.getElementById("kg-stage");
  var workbench = document.getElementById("kg-workbench");
  var loading = document.getElementById("kg-loading");
  var toast = document.getElementById("kg-toast");
  var searchInput = document.getElementById("kg-search");
  var kindFilter = document.getElementById("kg-kind-filter");
  var statusFilter = document.getElementById("kg-status-filter");
  var relationFilter = document.getElementById("kg-relation-filter");
  var inspectorEmpty = document.getElementById("kg-inspector-empty");
  var inspectorContent = document.getElementById("kg-inspector-content");
  var detailEyebrow = document.getElementById("kg-detail-eyebrow");
  var detailTitle = document.getElementById("kg-detail-title");
  var detailStatus = document.getElementById("kg-detail-status");
  var detailDescription = document.getElementById("kg-detail-description");
  var detailMeta = document.getElementById("kg-detail-meta");
  var detailAttributes = document.querySelector("#kg-detail-attributes pre");
  var editorialActions = document.getElementById("kg-editorial-actions");
  var nodeCount = document.getElementById("kg-node-count");
  var linkCount = document.getElementById("kg-link-count");
  var draftCount = document.getElementById("kg-draft-count");

  var STATUS_LABELS = { draft: "Esborrany", validated: "Validat", retired: "Retirat" };
  var DIRECTION_LABELS = {
    unknown: "No resolta",
    none: "Sense rotació transversal",
    forward: "Endavant",
    backward: "Enrere"
  };
  var RESOLUTION_LABELS = { explicit: "explícita", inferred: "inferida", unknown: "no resolta" };
  var POSITION_SYMBOL_LABELS = { o: "Agrupada", "<": "Carpada", "/": "Planxada" };
  var KIND_LABELS = {
    skill: "Element o habilitat",
    body_position: "Posició corporal",
    contact_position: "Posició de contacte",
    technical_component: "Component tècnic",
    error: "Error",
    exercise: "Exercici professional",
    quality: "Qualitat",
    risk: "Risc",
    goal: "Objectiu"
  };
  var KIND_COLORS = {
    skill: "#60a5fa",
    body_position: "#f472b6",
    contact_position: "#2dd4bf",
    technical_component: "#a78bfa",
    error: "#fb7185",
    exercise: "#34d399",
    quality: "#22d3ee",
    risk: "#f97316",
    goal: "#facc15"
  };
  var STATUS_COLORS = { draft: "#f59e0b", validated: "#10b981", retired: "#64748b" };
  var LINK_COLORS = {
    requires: "#fbbf24",
    progresses_to: "#60a5fa",
    has_defining_position: "#f472b6",
    starts_from_contact: "#22d3ee",
    ends_in_contact: "#2dd4bf",
    corrects: "#34d399",
    conditions: "#fb7185",
    trains: "#a78bfa"
  };
  var RELATION_LABELS = {
    requires: "requereix",
    progresses_to: "progressa cap a",
    has_defining_position: "té com a posició definitòria",
    starts_from_contact: "parteix del contacte",
    ends_in_contact: "acaba en el contacte",
    corrects: "corregeix",
    conditions: "condiciona",
    trains: "entrena"
  };

  var graph = { nodes: [], links: [], nodeById: new Map() };
  var camera = { yaw: 0.42, pitch: -0.26, zoom: 1, panX: 0, panY: 0 };
  var viewport = { width: 1, height: 1, dpr: 1 };
  var selected = null;
  var hovered = null;
  var paused = false;
  var groupByKind = false;
  var layoutEnergy = 1;
  var drag = null;
  var toastTimer = null;

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function showToast(message, isError) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle("is-error", Boolean(isError));
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 3400);
  }

  function normalizedText(value) {
    return String(value || "").toLocaleLowerCase("ca").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  function matchesSearch(node) {
    var query = normalizedText(searchInput.value.trim());
    if (!query) return true;
    return normalizedText([
      node.name,
      node.description,
      node.kind,
      JSON.stringify(node.attributes || {})
    ].join(" ")).indexOf(query) !== -1;
  }

  function nodePassesFilters(node) {
    return (!kindFilter.value || node.kind === kindFilter.value) &&
      (!statusFilter.value || node.status === statusFilter.value);
  }

  function refreshVisibility() {
    var hasSearch = Boolean(searchInput.value.trim());
    var matchedIds = new Set(
      graph.nodes.filter(function (node) {
        return nodePassesFilters(node) && (!hasSearch || matchesSearch(node));
      }).map(function (node) { return node.id; })
    );
    var contextualIds = new Set(matchedIds);
    if (hasSearch) {
      graph.links.forEach(function (link) {
        if (matchedIds.has(link.sourceNode.id) && nodePassesFilters(link.targetNode)) {
          contextualIds.add(link.targetNode.id);
        }
        if (matchedIds.has(link.targetNode.id) && nodePassesFilters(link.sourceNode)) {
          contextualIds.add(link.sourceNode.id);
        }
      });
    }
    graph.nodes.forEach(function (node) {
      node.visible = nodePassesFilters(node) && contextualIds.has(node.id);
    });
    graph.links.forEach(function (link) {
      link.visible = Boolean(
        link.sourceNode.visible &&
        link.targetNode.visible &&
        (!statusFilter.value || link.status === statusFilter.value) &&
        (!relationFilter.value || link.relationType === relationFilter.value) &&
        (!hasSearch || matchedIds.has(link.sourceNode.id) || matchedIds.has(link.targetNode.id))
      );
    });
    if (relationFilter.value) {
      var connectedIds = new Set();
      graph.links.filter(function (link) { return link.visible; }).forEach(function (link) {
        connectedIds.add(link.sourceNode.id);
        connectedIds.add(link.targetNode.id);
      });
      graph.nodes.forEach(function (node) {
        node.visible = node.visible && connectedIds.has(node.id);
      });
    }
    if (selected && !selected.item.visible) clearSelection();
    updateCounts();
    layoutEnergy = 0.6;
  }

  function updateCounts() {
    var visibleNodes = graph.nodes.filter(function (node) { return node.visible; });
    nodeCount.textContent = visibleNodes.length;
    linkCount.textContent = graph.links.filter(function (link) { return link.visible; }).length;
    draftCount.textContent = visibleNodes.filter(function (node) { return node.status === "draft"; }).length;
  }

  function initializePositions() {
    var goldenAngle = Math.PI * (3 - Math.sqrt(5));
    var count = Math.max(1, graph.nodes.length);
    graph.nodes.forEach(function (node, index) {
      var y = 1 - ((index + 0.5) / count) * 2;
      var radiusAtY = Math.sqrt(Math.max(0, 1 - y * y));
      var theta = goldenAngle * index;
      var radius = 215 + (index % 4) * 9;
      node.x = Math.cos(theta) * radiusAtY * radius;
      node.y = y * radius;
      node.z = Math.sin(theta) * radiusAtY * radius;
      node.vx = 0;
      node.vy = 0;
      node.vz = 0;
      node.visible = true;
      node.degree = 0;
    });
    graph.links.forEach(function (link) {
      link.sourceNode = graph.nodeById.get(Number(link.source));
      link.targetNode = graph.nodeById.get(Number(link.target));
      link.visible = Boolean(link.sourceNode && link.targetNode);
      if (link.sourceNode) link.sourceNode.degree += 1;
      if (link.targetNode) link.targetNode.degree += 1;
    });
  }

  function populateKindFilter() {
    var kinds = Array.from(new Set(graph.nodes.map(function (node) { return node.kind; }))).sort();
    kinds.forEach(function (kind) {
      var option = document.createElement("option");
      option.value = kind;
      option.textContent = KIND_LABELS[kind] || kind;
      kindFilter.appendChild(option);
    });
  }

  function populateRelationFilter() {
    var relationTypes = Array.from(new Set(graph.links.map(function (link) {
      return link.relationType;
    }))).sort();
    relationTypes.forEach(function (relationType) {
      var option = document.createElement("option");
      option.value = relationType;
      option.textContent = RELATION_LABELS[relationType] || relationType;
      relationFilter.appendChild(option);
    });
  }

  function clusterAnchor(kind) {
    var kinds = Array.from(new Set(graph.nodes.map(function (node) { return node.kind; }))).sort();
    var index = Math.max(0, kinds.indexOf(kind));
    var angle = (index / Math.max(1, kinds.length)) * Math.PI * 2;
    return { x: Math.cos(angle) * 160, y: Math.sin(angle) * 135, z: (index % 2 ? 1 : -1) * 75 };
  }

  function simulate() {
    if (paused || layoutEnergy < 0.002) return;
    var nodes = graph.nodes.filter(function (node) { return node.visible; });
    var links = graph.links.filter(function (link) { return link.visible; });
    var index;
    var otherIndex;

    for (index = 0; index < nodes.length; index += 1) {
      var node = nodes[index];
      for (otherIndex = index + 1; otherIndex < nodes.length; otherIndex += 1) {
        var other = nodes[otherIndex];
        var dx = node.x - other.x;
        var dy = node.y - other.y;
        var dz = node.z - other.z;
        var distanceSquared = dx * dx + dy * dy + dz * dz + 45;
        var inverseDistance = 1 / Math.sqrt(distanceSquared);
        var repulsion = (760 * layoutEnergy) / distanceSquared;
        var fx = dx * inverseDistance * repulsion;
        var fy = dy * inverseDistance * repulsion;
        var fz = dz * inverseDistance * repulsion;
        node.vx += fx;
        node.vy += fy;
        node.vz += fz;
        other.vx -= fx;
        other.vy -= fy;
        other.vz -= fz;
      }
    }

    links.forEach(function (link) {
      var dx = link.targetNode.x - link.sourceNode.x;
      var dy = link.targetNode.y - link.sourceNode.y;
      var dz = link.targetNode.z - link.sourceNode.z;
      var distance = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
      var pull = (distance - 118) * 0.0009 * layoutEnergy;
      var fx = (dx / distance) * pull;
      var fy = (dy / distance) * pull;
      var fz = (dz / distance) * pull;
      link.sourceNode.vx += fx;
      link.sourceNode.vy += fy;
      link.sourceNode.vz += fz;
      link.targetNode.vx -= fx;
      link.targetNode.vy -= fy;
      link.targetNode.vz -= fz;
    });

    nodes.forEach(function (node) {
      var anchor = groupByKind ? clusterAnchor(node.kind) : { x: 0, y: 0, z: 0 };
      var attraction = groupByKind ? 0.0011 : 0.00028;
      node.vx += (anchor.x - node.x) * attraction * layoutEnergy;
      node.vy += (anchor.y - node.y) * attraction * layoutEnergy;
      node.vz += (anchor.z - node.z) * attraction * layoutEnergy;
      node.vx *= 0.91;
      node.vy *= 0.91;
      node.vz *= 0.91;
      node.x += node.vx;
      node.y += node.vy;
      node.z += node.vz;
    });
    layoutEnergy *= 0.992;
  }

  function project(node) {
    var cosYaw = Math.cos(camera.yaw);
    var sinYaw = Math.sin(camera.yaw);
    var cosPitch = Math.cos(camera.pitch);
    var sinPitch = Math.sin(camera.pitch);
    var rotatedX = node.x * cosYaw + node.z * sinYaw;
    var yawZ = -node.x * sinYaw + node.z * cosYaw;
    var rotatedY = node.y * cosPitch - yawZ * sinPitch;
    var rotatedZ = node.y * sinPitch + yawZ * cosPitch;
    var depth = Math.max(260, 820 + rotatedZ);
    var perspective = (820 / depth) * camera.zoom;
    var baseScale = Math.min(viewport.width, viewport.height) / 610;
    return {
      x: viewport.width / 2 + camera.panX + rotatedX * baseScale * perspective,
      y: viewport.height / 2 + camera.panY + rotatedY * baseScale * perspective,
      z: rotatedZ,
      scale: clamp(perspective * baseScale, 0.45, 2.8)
    };
  }

  function drawArrow(link, source, target, color, width) {
    var dx = target.x - source.x;
    var dy = target.y - source.y;
    var length = Math.sqrt(dx * dx + dy * dy);
    if (length < 2) return;
    var targetRadius = (5.5 + Math.sqrt(link.targetNode.degree + 1) * 1.25) * target.scale;
    var ux = dx / length;
    var uy = dy / length;
    var endX = target.x - ux * (targetRadius + 2);
    var endY = target.y - uy * (targetRadius + 2);
    context.beginPath();
    context.moveTo(source.x, source.y);
    context.lineTo(endX, endY);
    context.strokeStyle = color;
    context.lineWidth = width;
    context.setLineDash(link.status === "draft" ? [5, 4] : (link.status === "retired" ? [2, 5] : []));
    context.stroke();
    context.setLineDash([]);

    var arrowSize = 5 + width;
    context.beginPath();
    context.moveTo(endX, endY);
    context.lineTo(endX - ux * arrowSize - uy * arrowSize * 0.65, endY - uy * arrowSize + ux * arrowSize * 0.65);
    context.lineTo(endX - ux * arrowSize + uy * arrowSize * 0.65, endY - uy * arrowSize - ux * arrowSize * 0.65);
    context.closePath();
    context.fillStyle = color;
    context.fill();
  }

  function drawLabel(text, x, y, color) {
    context.font = "600 11px Poppins, Segoe UI, sans-serif";
    var width = context.measureText(text).width + 12;
    context.fillStyle = "rgba(7, 17, 31, .86)";
    context.fillRect(x - width / 2, y - 22, width, 17);
    context.fillStyle = color || "#e2e8f0";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(text, x, y - 13.5);
  }

  function render() {
    context.clearRect(0, 0, viewport.width, viewport.height);
    graph.nodes.forEach(function (node) { node.screen = project(node); });

    graph.links.filter(function (link) { return link.visible; }).forEach(function (link) {
      var isSelected = selected && selected.type === "link" && selected.item.id === link.id;
      var isHovered = hovered && hovered.type === "link" && hovered.item.id === link.id;
      var baseColor = LINK_COLORS[link.relationType] || "#64748b";
      var alpha = isSelected || isHovered ? "ff" : "7a";
      drawArrow(link, link.sourceNode.screen, link.targetNode.screen, baseColor + alpha, isSelected ? 2.4 : 1.15);
      link.screen = {
        x1: link.sourceNode.screen.x,
        y1: link.sourceNode.screen.y,
        x2: link.targetNode.screen.x,
        y2: link.targetNode.screen.y,
        z: (link.sourceNode.screen.z + link.targetNode.screen.z) / 2
      };
      if (isSelected || isHovered) {
        drawLabel(RELATION_LABELS[link.relationType] || link.relationType, (link.screen.x1 + link.screen.x2) / 2, (link.screen.y1 + link.screen.y2) / 2, "#d8b4fe");
      }
    });

    var visibleNodes = graph.nodes.filter(function (node) { return node.visible; }).sort(function (a, b) {
      return a.screen.z - b.screen.z;
    });
    visibleNodes.forEach(function (node) {
      var isSelected = selected && selected.type === "node" && selected.item.id === node.id;
      var isHovered = hovered && hovered.type === "node" && hovered.item.id === node.id;
      var radius = (5.5 + Math.sqrt(node.degree + 1) * 1.25) * node.screen.scale;
      node.screen.radius = radius;
      context.beginPath();
      context.arc(node.screen.x, node.screen.y, radius + (isSelected ? 5 : 3), 0, Math.PI * 2);
      context.fillStyle = isSelected ? "rgba(255,255,255,.3)" : STATUS_COLORS[node.status] || "#64748b";
      context.fill();
      context.beginPath();
      context.arc(node.screen.x, node.screen.y, radius, 0, Math.PI * 2);
      context.fillStyle = node.status === "retired" ? "#475569" : (KIND_COLORS[node.kind] || "#60a5fa");
      context.shadowColor = isSelected || isHovered ? "rgba(196,181,253,.9)" : "rgba(96,165,250,.28)";
      context.shadowBlur = isSelected || isHovered ? 18 : 8;
      context.fill();
      context.shadowBlur = 0;
      context.lineWidth = 1;
      context.strokeStyle = "rgba(255,255,255,.72)";
      context.stroke();
      if (isSelected || isHovered || (camera.zoom > 1.45 && visibleNodes.length < 80) || (searchInput.value && matchesSearch(node))) {
        drawLabel(node.name, node.screen.x, node.screen.y - radius - 2, isSelected ? "#fff" : "#dbeafe");
      }
    });
  }

  function animationFrame() {
    simulate();
    render();
    window.requestAnimationFrame(animationFrame);
  }

  function resizeCanvas() {
    var rect = stage.getBoundingClientRect();
    viewport.width = Math.max(1, rect.width);
    viewport.height = Math.max(1, rect.height);
    viewport.dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(viewport.width * viewport.dpr);
    canvas.height = Math.round(viewport.height * viewport.dpr);
    canvas.style.width = viewport.width + "px";
    canvas.style.height = viewport.height + "px";
    context.setTransform(viewport.dpr, 0, 0, viewport.dpr, 0, 0);
  }

  function distanceToSegment(px, py, x1, y1, x2, y2) {
    var dx = x2 - x1;
    var dy = y2 - y1;
    if (dx === 0 && dy === 0) return Math.hypot(px - x1, py - y1);
    var t = clamp(((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy), 0, 1);
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }

  function itemAt(x, y) {
    var nodes = graph.nodes.filter(function (node) { return node.visible; }).sort(function (a, b) {
      return b.screen.z - a.screen.z;
    });
    for (var index = 0; index < nodes.length; index += 1) {
      var node = nodes[index];
      if (Math.hypot(x - node.screen.x, y - node.screen.y) <= node.screen.radius + 7) {
        return { type: "node", item: node };
      }
    }
    var links = graph.links.filter(function (link) { return link.visible && link.screen; });
    for (var linkIndex = 0; linkIndex < links.length; linkIndex += 1) {
      var link = links[linkIndex];
      if (distanceToSegment(x, y, link.screen.x1, link.screen.y1, link.screen.x2, link.screen.y2) < 6) {
        return { type: "link", item: link };
      }
    }
    return null;
  }

  function pointerPosition(event) {
    var rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function addMeta(label, value) {
    var wrapper = document.createElement("div");
    var term = document.createElement("dt");
    var description = document.createElement("dd");
    term.textContent = label;
    description.textContent = value || "—";
    wrapper.appendChild(term);
    wrapper.appendChild(description);
    detailMeta.appendChild(wrapper);
  }

  function showInspector(selection) {
    selected = selection;
    inspectorEmpty.hidden = true;
    inspectorContent.hidden = false;
    detailMeta.replaceChildren();
    var item = selection.item;
    detailStatus.textContent = STATUS_LABELS[item.status] || item.status;
    detailStatus.dataset.status = item.status;

    if (selection.type === "node") {
      detailEyebrow.textContent = KIND_LABELS[item.kind] || item.kind;
      detailTitle.textContent = item.name;
      detailDescription.textContent = item.description || "Sense descripció editorial.";
      addMeta("Disciplina", item.discipline);
      addMeta("Autoria", item.author);
      addMeta("Actualitzat", new Date(item.updatedAt).toLocaleString("ca-ES"));
      if (item.rotation) {
        addMeta("Notació original", item.rotation.rawNotation || "No disponible");
        addMeta("Notació normalitzada", item.rotation.normalizedNotation || "No resolta");
        addMeta(
          "Rotació transversal",
          item.rotation.transverseQuarters + " quarts · " +
            (DIRECTION_LABELS[item.rotation.transverseDirection] || item.rotation.transverseDirection) +
            " (" + (RESOLUTION_LABELS[item.rotation.directionSource] || item.rotation.directionSource) + ")"
        );
        addMeta("Mig girs longitudinals", "[" + item.rotation.halfTurns.join(", ") + "]");
        addMeta(
          "Posició a la notació",
          item.rotation.positionSymbol
            ? (POSITION_SYMBOL_LABELS[item.rotation.positionSymbol] || item.rotation.positionSymbol) +
              " (" + (RESOLUTION_LABELS[item.rotation.positionSource] || item.rotation.positionSource) + ")"
            : "No indicada"
        );
        addMeta("Estat de la rotació", STATUS_LABELS[item.rotation.status] || item.rotation.status);
      }
      detailAttributes.parentElement.hidden = false;
      detailAttributes.textContent = JSON.stringify(item.attributes || {}, null, 2);
    } else {
      detailEyebrow.textContent = "Relació dirigida";
      detailTitle.textContent = item.sourceNode.name + " → " + item.targetNode.name;
      detailDescription.textContent = item.rationale || "Sense justificació editorial.";
      addMeta("Tipus", RELATION_LABELS[item.relationType] || item.relationType);
      addMeta("Origen", item.sourceNode.name);
      addMeta("Destí", item.targetNode.name);
      addMeta("Autoria", item.author);
      addMeta("Actualitzada", new Date(item.updatedAt).toLocaleString("ca-ES"));
      detailAttributes.parentElement.hidden = true;
    }
    editorialActions.querySelectorAll("button[data-status]").forEach(function (button) {
      button.classList.toggle("is-current", button.dataset.status === item.status);
    });
  }

  function clearSelection() {
    selected = null;
    inspectorEmpty.hidden = false;
    inspectorContent.hidden = true;
  }

  function focusSelection() {
    if (!selected) return;
    var target;
    if (selected.type === "node") {
      target = selected.item.screen;
    } else {
      target = {
        x: (selected.item.screen.x1 + selected.item.screen.x2) / 2,
        y: (selected.item.screen.y1 + selected.item.screen.y2) / 2
      };
    }
    camera.panX -= target.x - viewport.width / 2;
    camera.panY -= target.y - viewport.height / 2;
    camera.zoom = Math.max(camera.zoom, 1.45);
  }

  function resetCamera() {
    camera.yaw = 0.42;
    camera.pitch = -0.26;
    camera.zoom = 1;
    camera.panX = 0;
    camera.panY = 0;
  }

  async function updateEditorialStatus(status) {
    if (!selected) return;
    var item = selected.item;
    var template = selected.type === "node" ? app.dataset.nodeStatusUrl : app.dataset.linkStatusUrl;
    var url = template.replace(/\/0\/estat\/$/, "/" + item.id + "/estat/");
    var buttons = editorialActions.querySelectorAll("button[data-status]");
    buttons.forEach(function (button) { button.disabled = true; });
    try {
      var response = await window.fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": app.dataset.csrfToken },
        body: JSON.stringify({ status: status })
      });
      var payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No s'ha pogut actualitzar l'estat.");
      Object.assign(item, selected.type === "node" ? payload.node : payload.link);
      showInspector(selected);
      updateCounts();
      showToast("Estat editorial actualitzat a «" + (STATUS_LABELS[status] || status) + "».");
    } catch (error) {
      showToast(error.message, true);
    } finally {
      buttons.forEach(function (button) { button.disabled = false; });
    }
  }

  canvas.addEventListener("pointerdown", function (event) {
    var position = pointerPosition(event);
    drag = {
      pointerId: event.pointerId,
      lastX: position.x,
      lastY: position.y,
      startX: position.x,
      startY: position.y,
      moved: false,
      mode: event.ctrlKey ? "rotate" : "pan"
    };
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add("is-dragging");
  });

  canvas.addEventListener("pointermove", function (event) {
    var position = pointerPosition(event);
    if (!drag) {
      hovered = itemAt(position.x, position.y);
      canvas.style.cursor = hovered ? "pointer" : "grab";
      return;
    }
    var dx = position.x - drag.lastX;
    var dy = position.y - drag.lastY;
    if (Math.hypot(position.x - drag.startX, position.y - drag.startY) > 3) drag.moved = true;
    if (drag.mode === "rotate") {
      camera.yaw += dx * 0.008;
      camera.pitch = clamp(camera.pitch + dy * 0.008, -Math.PI / 2 + 0.04, Math.PI / 2 - 0.04);
    } else {
      camera.panX += dx;
      camera.panY += dy;
    }
    drag.lastX = position.x;
    drag.lastY = position.y;
  });

  function finishDrag(event) {
    if (!drag || drag.pointerId !== event.pointerId) return;
    var position = pointerPosition(event);
    if (!drag.moved) {
      var hit = itemAt(position.x, position.y);
      if (hit) showInspector(hit); else clearSelection();
    }
    drag = null;
    canvas.classList.remove("is-dragging");
    canvas.style.cursor = hovered ? "pointer" : "grab";
  }

  canvas.addEventListener("pointerup", finishDrag);
  canvas.addEventListener("pointercancel", finishDrag);
  canvas.addEventListener("pointerleave", function () { if (!drag) hovered = null; });
  canvas.addEventListener("dblclick", function (event) {
    var position = pointerPosition(event);
    var hit = itemAt(position.x, position.y);
    if (hit) {
      showInspector(hit);
      focusSelection();
    }
  });
  canvas.addEventListener("wheel", function (event) {
    event.preventDefault();
    camera.zoom = clamp(camera.zoom * Math.exp(-event.deltaY * 0.0012), 0.35, 4.8);
  }, { passive: false });
  canvas.addEventListener("keydown", function (event) {
    if (event.key === "+" || event.key === "=") camera.zoom = clamp(camera.zoom * 1.16, 0.35, 4.8);
    if (event.key === "-") camera.zoom = clamp(camera.zoom / 1.16, 0.35, 4.8);
    if (event.key.toLowerCase() === "r") resetCamera();
  });

  searchInput.addEventListener("input", refreshVisibility);
  kindFilter.addEventListener("change", refreshVisibility);
  statusFilter.addEventListener("change", refreshVisibility);
  relationFilter.addEventListener("change", refreshVisibility);
  document.getElementById("kg-group").addEventListener("click", function (event) {
    groupByKind = !groupByKind;
    event.currentTarget.setAttribute("aria-pressed", String(groupByKind));
    layoutEnergy = 1;
  });
  document.getElementById("kg-pause").addEventListener("click", function (event) {
    paused = !paused;
    event.currentTarget.setAttribute("aria-pressed", String(paused));
    event.currentTarget.textContent = paused ? "Reprèn" : "Pausa";
  });
  document.getElementById("kg-zoom-in").addEventListener("click", function () { camera.zoom = clamp(camera.zoom * 1.2, 0.35, 4.8); });
  document.getElementById("kg-zoom-out").addEventListener("click", function () { camera.zoom = clamp(camera.zoom / 1.2, 0.35, 4.8); });
  document.getElementById("kg-reset").addEventListener("click", resetCamera);
  document.getElementById("kg-fullscreen").addEventListener("click", function () {
    if (document.fullscreenElement) document.exitFullscreen(); else workbench.requestFullscreen();
  });
  document.getElementById("kg-close-detail").addEventListener("click", clearSelection);
  document.getElementById("kg-focus").addEventListener("click", focusSelection);
  editorialActions.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-status]");
    if (button) updateEditorialStatus(button.dataset.status);
  });

  var resizeObserver = new ResizeObserver(resizeCanvas);
  resizeObserver.observe(stage);
  resizeCanvas();

  window.fetch(app.dataset.graphUrl, { credentials: "same-origin" })
    .then(function (response) {
      if (!response.ok) throw new Error("No s'han pogut carregar les dades del graf.");
      return response.json();
    })
    .then(function (payload) {
      graph.nodes = payload.nodes || [];
      graph.links = payload.links || [];
      graph.nodeById = new Map(graph.nodes.map(function (node) { return [Number(node.id), node]; }));
      initializePositions();
      populateKindFilter();
      populateRelationFilter();
      refreshVisibility();
      loading.hidden = true;
      animationFrame();
    })
    .catch(function (error) {
      loading.textContent = error.message;
      loading.style.color = "#fecaca";
    });
}());
