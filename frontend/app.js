/**
 * ResilienceOS Application Controller.
 * Manages order scheduling, dynamic programming execution, timeline rendering,
 * generator fuel ROI analysis, presets, CSV import/export, and kitchen work orders.
 */

const defaultJobs = [
  { id: 'Bread batch', duration: 4, deadline: 9, missed_penalty: 4600 },
  { id: 'Birthday cakes', duration: 5, deadline: 8, missed_penalty: 7800 },
  { id: 'Biscuits', duration: 3, deadline: 19, missed_penalty: 2400 },
  { id: 'Pastries', duration: 4, deadline: 16, missed_penalty: 3900 },
  { id: 'Tea cakes', duration: 3, deadline: 23, missed_penalty: 2100 }
];

const $ = id => document.getElementById(id);

let jobs = [];
let latestResult = null;

const money = v => 'Rs ' + Number(v || 0).toLocaleString('en-PK');
const slotLabel = slot => {
  const hr = Math.floor(slot / 2);
  const min = slot % 2 ? '30' : '00';
  return `${hr.toString().padStart(2, '0')}:${min}`;
};

// Render orders in table
function renderJobs() {
  const countEl = $('jobCount');
  if (countEl) countEl.textContent = `${jobs.length} ORDERS`;
  const tbody = $('jobRows');
  if (!tbody) return;
  tbody.replaceChildren();

  for (const [idx, job] of jobs.entries()) {
    const row = document.createElement('tr');

    // 1. Order Name
    const tdName = document.createElement('td');
    const inputName = document.createElement('input');
    inputName.type = 'text';
    inputName.value = job.id;
    inputName.setAttribute('aria-label', `Order name ${idx + 1}`);
    inputName.onchange = () => {
      jobs[idx].id = inputName.value.trim() || `Order ${idx + 1}`;
    };
    tdName.append(inputName);

    // Risk indicator
    if (job.missed_penalty >= 5000) {
      const tag = document.createElement('span');
      tag.className = 'risk-badge risk-high';
      tag.textContent = 'HIGH VALUE';
      tdName.append(tag);
    }
    row.append(tdName);

    // 2. Duration
    const tdDur = document.createElement('td');
    const inputDur = document.createElement('input');
    inputDur.type = 'number';
    inputDur.min = '1';
    inputDur.max = '24';
    inputDur.value = job.duration;
    inputDur.onchange = () => {
      jobs[idx].duration = Math.max(1, Math.min(24, Number(inputDur.value)));
    };
    tdDur.append(inputDur);
    row.append(tdDur);

    // 3. Deadline
    const tdDue = document.createElement('td');
    const inputDue = document.createElement('input');
    inputDue.type = 'number';
    inputDue.min = '1';
    inputDue.max = '24';
    inputDue.value = job.deadline;
    inputDue.onchange = () => {
      jobs[idx].deadline = Math.max(1, Math.min(24, Number(inputDue.value)));
    };
    tdDue.append(inputDue);
    row.append(tdDue);

    // 4. Missed Penalty
    const tdPen = document.createElement('td');
    const inputPen = document.createElement('input');
    inputPen.type = 'number';
    inputPen.min = '0';
    inputPen.max = '1000000';
    inputPen.value = job.missed_penalty;
    inputPen.onchange = () => {
      jobs[idx].missed_penalty = Math.max(0, Number(inputPen.value));
    };
    tdPen.append(inputPen);
    row.append(tdPen);

    // 5. Delete Action
    const tdDel = document.createElement('td');
    const delBtn = document.createElement('button');
    delBtn.className = 'remove';
    delBtn.textContent = '×';
    delBtn.title = 'Remove this order';
    delBtn.onclick = () => {
      jobs.splice(idx, 1);
      renderJobs();
    };
    tdDel.append(delBtn);
    row.append(tdDel);

    tbody.append(row);
  }
}

// Add new order
$('addJob').onclick = () => {
  if (jobs.length >= 12) {
    $('error').textContent = 'Maximum limit of 12 orders reached for a single production shift.';
    return;
  }
  const nextNum = jobs.length + 1;
  jobs.push({
    id: `Batch #${nextNum}`,
    duration: 3,
    deadline: 18,
    missed_penalty: 3500
  });
  $('error').textContent = '';
  renderJobs();
};

// Preset scenarios
document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.onclick = () => {
    const start = Number(btn.getAttribute('data-start'));
    const dur = Number(btn.getAttribute('data-dur'));
    $('outageStart').value = start;
    $('outageDuration').value = dur;
    run();
  };
});

// Generator Backup Toggle & ROI calculation visibility
const backupToggle = $('backup');
const generatorBox = $('generatorBox');
if (backupToggle && generatorBox) {
  backupToggle.onchange = () => {
    generatorBox.hidden = !backupToggle.checked;
    run();
  };
}

// Render Timeline Block
function addTimeline(parent, title, plan, result, isBaseline) {
  const outer = document.createElement('div');
  outer.className = 'timeline-block';

  const titleEl = document.createElement('div');
  titleEl.className = 'timeline-name';
  titleEl.innerHTML = `<span>${title}</span> <span style="font-weight:400;color:#91a7bf;">${money(plan.loss)} total risk · ${plan.completed} completed</span>`;
  outer.append(titleEl);

  // Time ruler
  const ruler = document.createElement('div');
  ruler.className = 'ruler';
  for (let i = 0; i < 24; i++) {
    const s = document.createElement('span');
    s.textContent = i % 2 === 0 ? slotLabel(i) : '';
    ruler.append(s);
  }
  outer.append(ruler);

  // Time track
  const track = document.createElement('div');
  track.className = 'time-row';

  const outage = result.scenario;
  if (outage.outage_duration && !outage.backup) {
    const outageEl = document.createElement('div');
    outageEl.className = 'time-outage';
    outageEl.style.gridColumn = `${outage.outage_start + 1} / span ${outage.outage_duration}`;
    outageEl.title = `Power Outage: ${slotLabel(outage.outage_start)} to ${slotLabel(outage.outage_start + outage.outage_duration)}`;
    track.append(outageEl);
  }

  for (const item of plan.schedule) {
    const jobEl = document.createElement('div');
    jobEl.className = 'time-job' + (isBaseline ? ' alt' : '');
    jobEl.style.gridColumn = `${item.start + 1} / span ${item.end - item.start}`;
    jobEl.style.gridRow = '1';
    jobEl.textContent = item.id;
    jobEl.title = `${item.id}: ${slotLabel(item.start)} – ${slotLabel(item.end)}`;
    track.append(jobEl);
  }

  outer.append(track);
  parent.append(outer);
}

// Render Results and Insights
function renderResult(result) {
  latestResult = result;

  $('baselineLoss').textContent = money(result.baseline.loss);
  $('optimizedLoss').textContent = money(result.optimized.loss);
  $('savings').textContent = money(result.savings);
  $('savingsHint').textContent = `${result.improvement_percent}% lower modeled loss`;
  $('recovered').textContent = '+' + Math.max(0, result.optimized.completed - result.baseline.completed);

  // Render Timelines
  const timeline = $('timelineContainer');
  timeline.className = '';
  timeline.replaceChildren();

  addTimeline(timeline, 'Original Baseline · First-Come, First-Served', result.baseline, result, true);
  addTimeline(timeline, 'ResilienceOS · Mathematically Optimal Sequence', result.optimized, result, false);

  // Generator ROI Result
  const roiBox = $('generatorRoiResult');
  if (result.generator_roi && roiBox) {
    const roi = result.generator_roi;
    roiBox.className = `roi-result-card ${roi.is_beneficial ? '' : 'negative'}`;
    roiBox.innerHTML = `
      <div>
        <span>Outage Fuel: <strong>${roi.fuel_liters} L</strong> (${money(roi.fuel_cost_pkr)})</span><br>
        <span>Prevented Penalties: <strong>${money(result.savings)}</strong></span>
      </div>
      <div style="text-align:right;">
        <span style="font-size:10px;text-transform:uppercase;color:#8da4be;">Net Financial Benefit</span><br>
        <strong style="font-size:16px;color:${roi.is_beneficial ? '#70e2c2' : '#ff7875'};">
          ${roi.is_beneficial ? '+' : ''}${money(roi.net_benefit_pkr)}
        </strong>
      </div>
    `;
  }

  // Render Insights
  const insight = $('insightBody');
  insight.className = '';
  insight.replaceChildren();

  const messages = [];
  if (result.savings > 0) {
    messages.push(`The optimal sequence reduces total financial risk by ${money(result.savings)} (${result.improvement_percent}%) compared with simple first-come-first-served scheduling.`);
  } else {
    messages.push('Your baseline plan is already optimal for this scenario. No unnecessary schedule disruptions are advised.');
  }

  if (result.optimized.schedule.length) {
    messages.push('Recommended baking dispatch order: ' + result.optimized.schedule.map(j => `<strong>${j.id}</strong>`).join(' → ') + '.');
  }

  if (result.optimized.missed.length) {
    messages.push(`Orders unable to fit in shift due to outage: <span style="color:#ff8585;">${result.optimized.missed.join(', ')}</span>. Prepare customer notifications in advance.`);
  } else {
    messages.push('All orders can be successfully completed within the 12-hour shift.');
  }

  if (result.generator_roi) {
    const roi = result.generator_roi;
    if (roi.is_beneficial) {
      messages.push(`Operating backup generator is highly cost-effective: saved penalties exceed fuel cost by ${money(roi.net_benefit_pkr)}.`);
    } else {
      messages.push(`Warning: Generator fuel cost (${money(roi.fuel_cost_pkr)}) exceeds late penalties saved (${money(result.savings)}). Consider prioritizing critical batches only.`);
    }
  }

  for (const msg of messages) {
    const item = document.createElement('div');
    item.className = 'insight';
    item.innerHTML = `<span class="bullet">✦</span> <span>${msg}</span>`;
    insight.append(item);
  }

  // Render Technical Transparency
  const tech = $('techBody');
  if (tech) {
    tech.replaceChildren();
    const metrics = [
      ['Solver Algorithm', result.algorithm],
      ['Solver Status', result.solver_status],
      ['States Explored (Memoized DP)', result.states_explored.toLocaleString()],
      ['Late Completion Penalties', money(result.optimized.late_cost)],
      ['Missed Order Penalties', money(result.optimized.missed_cost)],
      ['Total Optimized Risk', money(result.optimized.loss)],
      ['Production Capacity', 'Single Oven / Production Line'],
      ['Mathematical Proof', 'Exact optimality guaranteed']
    ];
    for (const [label, val] of metrics) {
      const line = document.createElement('div');
      line.className = 'technical-line';
      line.innerHTML = `<span>${label}</span> <strong>${val}</strong>`;
      tech.append(line);
    }
  }
}

// Run Optimization
async function run() {
  const btn = $('run');
  btn.disabled = true;
  btn.textContent = 'Calculating optimal schedule…';
  $('error').textContent = '';

  try {
    const payload = {
      outage_start: Number($('outageStart').value),
      outage_duration: Number($('outageDuration').value),
      late_rate: Number($('lateRate').value),
      backup: $('backup').checked,
      fuel_rate: Number($('fuelRate')?.value || 0),
      fuel_price: Number($('fuelPrice')?.value || 0),
      jobs
    };

    const res = await fetch('/api/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Optimization failed.');

    renderResult(data);

    // Save simulation to current user's history
    if (typeof window.persistSimulation === 'function') {
      await window.persistSimulation(payload, data);
    }
  } catch (err) {
    $('error').textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '✦ &nbsp; Run optimization <span>→</span>';
  }
}
$('run').onclick = run;

// Load Sample Data Button
$('loadDemo').onclick = () => {
  jobs = structuredClone(defaultJobs);
  renderJobs();
  $('outageStart').value = 6;
  $('outageDuration').value = 5;
  $('lateRate').value = 350;
  $('backup').checked = false;
  if ($('generatorBox')) $('generatorBox').hidden = true;
  run();
};

// Printable Kitchen Work Order Dispatch
$('printWorkOrder').onclick = () => {
  if (!latestResult || !latestResult.optimized.schedule.length) {
    alert('Please run an optimization first to generate the kitchen work order.');
    return;
  }
  window.print();
};

// CSV Export
$('exportCsv').onclick = () => {
  if (!jobs.length) {
    alert('No orders to export.');
    return;
  }
  let csv = 'Order Name,Duration Slots (30m),Due Slot,Missed Penalty (PKR)\n';
  for (const j of jobs) {
    csv += `"${j.id.replace(/"/g, '""')}",${j.duration},${j.deadline},${j.missed_penalty}\n`;
  }
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `resilienceos-orders-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
};

// CSV Import
$('importCsvBtn').onclick = () => $('csvFileInput').click();
$('csvFileInput').onchange = (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (evt) => {
    try {
      const text = evt.target.result;
      const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
      if (lines.length < 2) throw new Error('CSV must have a header and at least one order.');

      const parsedJobs = [];
      for (let i = 1; i < lines.length && parsedJobs.length < 12; i++) {
        const parts = lines[i].split(',').map(p => p.trim().replace(/^"|"$/g, ''));
        if (parts.length >= 4) {
          parsedJobs.push({
            id: parts[0] || `Order ${i}`,
            duration: Math.max(1, Math.min(24, parseInt(parts[1], 10) || 2)),
            deadline: Math.max(1, Math.min(24, parseInt(parts[2], 10) || 12)),
            missed_penalty: Math.max(0, parseInt(parts[3], 10) || 2000)
          });
        }
      }

      if (!parsedJobs.length) throw new Error('No valid orders found in CSV.');
      jobs = parsedJobs;
      renderJobs();
      run();
      alert(`Successfully imported ${jobs.length} orders from CSV!`);
    } catch (err) {
      alert('CSV Import error: ' + err.message);
    }
  };
  reader.readAsText(file);
};

// Export JSON Scenario
$('exportScenario').onclick = () => {
  const data = {
    outage_start: Number($('outageStart').value),
    outage_duration: Number($('outageDuration').value),
    late_rate: Number($('lateRate').value),
    backup: $('backup').checked,
    fuel_rate: Number($('fuelRate')?.value || 0),
    fuel_price: Number($('fuelPrice')?.value || 0),
    jobs,
    latest_result: latestResult
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `resilienceos-scenario-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
};

// Initial Render
renderJobs();
