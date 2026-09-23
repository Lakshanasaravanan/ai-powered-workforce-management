import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { CircleAlert, Pencil, Plus, RefreshCw, Search, ShieldCheck, UserCheck, Users, X } from 'lucide-react';
import { employees, type Employee } from './lib/api';

type EmployeeForm = {
  employee_code: string;
  full_name: string;
  company_email: string;
  role: string;
  designation: string;
  department: string;
  manager_id: string;
};

const emptyForm: EmployeeForm = { employee_code: '', full_name: '', company_email: '', role: 'EMPLOYEE', designation: '', department: '', manager_id: '' };
const roleLabel = (role: string) => role[0] + role.slice(1).toLowerCase();

function EmployeeFields({ value, managers, onChange, editing }: { value: EmployeeForm; managers: Employee[]; onChange: (next: EmployeeForm) => void; editing?: Employee | null }) {
  const eligibleManagers = managers.filter((manager) => manager.is_active && manager.id !== editing?.id);
  return <div className="employee-form-grid">{!editing && <><label htmlFor="employee-code">Employee code<input id="employee-code" value={value.employee_code} onChange={(event) => onChange({ ...value, employee_code: event.target.value })} required /></label><label htmlFor="employee-email">Company email<input id="employee-email" type="email" value={value.company_email} onChange={(event) => onChange({ ...value, company_email: event.target.value })} required /></label></>}<label htmlFor="employee-name">Full name<input id="employee-name" value={value.full_name} onChange={(event) => onChange({ ...value, full_name: event.target.value })} required /></label><label htmlFor="employee-role">Role<select id="employee-role" value={value.role} onChange={(event) => onChange({ ...value, role: event.target.value })}><option value="EMPLOYEE">Employee</option><option value="MANAGER">Manager</option><option value="ADMIN">Admin</option></select></label><label htmlFor="employee-designation">Designation<input id="employee-designation" value={value.designation} onChange={(event) => onChange({ ...value, designation: event.target.value })} required /></label><label htmlFor="employee-department">Department<input id="employee-department" value={value.department} onChange={(event) => onChange({ ...value, department: event.target.value })} required /></label><label className="employee-manager-field" htmlFor="employee-manager">Manager <span>(optional)</span><select id="employee-manager" value={value.manager_id} onChange={(event) => onChange({ ...value, manager_id: event.target.value })}><option value="">No manager</option>{eligibleManagers.map((manager) => <option key={manager.id} value={manager.id}>{manager.full_name} · {manager.employee_code}</option>)}</select></label></div>;
}

export default function Employees() {
  const [list, setList] = useState<Employee[]>([]);
  const [form, setForm] = useState<EmployeeForm>(emptyForm);
  const [editing, setEditing] = useState<Employee | null>(null);
  const [query, setQuery] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [temporaryCredential, setTemporaryCredential] = useState('');

  const load = async (search = query) => {
    setLoading(true);
    setError('');
    try {
      setList(search.trim() ? await employees.search(search.trim()) : await employees.list());
    } catch {
      setError('Unable to load employees. Please try again.');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(''); }, []);
  const managers = useMemo(() => list.filter((employee) => employee.role === 'MANAGER'), [list]);

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const created = await employees.create({ ...form, manager_id: form.manager_id || null });
      setTemporaryCredential(created.temporary_password);
      setForm(emptyForm);
      setCreateOpen(false);
      await load('');
    } catch {
      setError('Unable to add this employee. Please review the details and try again.');
    } finally {
      setBusy(false);
    }
  };

  const update = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError('');
    try {
      await employees.update(editing.id, { full_name: editing.full_name, role: editing.role, designation: editing.designation, department: editing.department, manager_id: editing.manager_id, is_active: editing.is_active });
      setEditing(null);
      await load('');
    } catch {
      setError('Unable to update this employee. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (employee: Employee) => {
    setBusy(true);
    setError('');
    try {
      await employees.update(employee.id, { is_active: !employee.is_active });
      await load('');
    } catch {
      setError('Unable to update employee status. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const editValue: EmployeeForm | null = editing ? { employee_code: editing.employee_code, full_name: editing.full_name, company_email: editing.company_email, role: editing.role, designation: editing.designation, department: editing.department, manager_id: editing.manager_id ?? '' } : null;
  return <main className="workspace-page employees-workspace"><header className="page-header employees-page-header"><div><p className="eyebrow">Administration</p><h1>Employees</h1><p className="muted">Manage employee records and workplace access.</p></div><div><button type="button" onClick={() => { setCreateOpen((open) => !open); setEditing(null); }}><Plus size={17} /> Add employee</button><button type="button" className="button-secondary" aria-label="Refresh employees" disabled={loading} onClick={() => void load()}><RefreshCw size={16} className={loading ? 'spin' : ''} /></button></div></header>
    <p className="employees-note"><ShieldCheck size={16} aria-hidden="true" /> Google Workspace provisioning will be integrated in a later phase.</p>
    {error && <p className="error" role="alert"><CircleAlert size={16} /> {error}</p>}
    {temporaryCredential && <section className="temporary-credential" aria-label="Temporary onboarding credential"><div><p className="eyebrow">Employee created</p><h2>Temporary onboarding credential</h2><p>Share this credential securely. It is shown here once and is not stored in the browser.</p><code>{temporaryCredential}</code></div><button type="button" className="button-secondary" onClick={() => setTemporaryCredential('')}><X size={16} /> Dismiss</button></section>}
    {createOpen && <section className="employee-editor-card"><header><div><p className="eyebrow">New employee</p><h2>Add employee</h2></div><button type="button" className="button-secondary button-small" disabled={busy} onClick={() => setCreateOpen(false)}><X size={15} /> Close</button></header><form onSubmit={create}><EmployeeFields value={form} managers={managers} onChange={setForm} /><div className="employee-editor-actions"><button type="button" className="button-secondary" disabled={busy} onClick={() => setCreateOpen(false)}>Cancel</button><button disabled={busy} type="submit">{busy ? <><RefreshCw size={16} className="spin" /> Adding</> : 'Add employee'}</button></div></form></section>}
    {editing && editValue && <section className="employee-editor-card"><header><div><p className="eyebrow">Employee record</p><h2>Edit {editing.full_name}</h2></div><button type="button" className="button-secondary button-small" disabled={busy} onClick={() => setEditing(null)}><X size={15} /> Close</button></header><form onSubmit={update}><EmployeeFields value={editValue} managers={managers} editing={editing} onChange={(next) => setEditing({ ...editing, full_name: next.full_name, role: next.role, designation: next.designation, department: next.department, manager_id: next.manager_id || null })} /><label className="employee-active-toggle" htmlFor="employee-active"><input id="employee-active" type="checkbox" checked={editing.is_active} onChange={(event) => setEditing({ ...editing, is_active: event.target.checked })} /> Employee account is active</label><div className="employee-editor-actions"><button type="button" className="button-secondary" disabled={busy} onClick={() => setEditing(null)}>Cancel</button><button disabled={busy} type="submit">{busy ? <><RefreshCw size={16} className="spin" /> Saving</> : 'Save changes'}</button></div></form></section>}
    <section className="employee-directory"><header><div><h2>Employee directory</h2><p>{loading ? 'Loading employees…' : String(list.length) + ' employee' + (list.length === 1 ? '' : 's')}</p></div><label className="employee-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search employees</span><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void load(event.currentTarget.value); } }} placeholder="Search employees" /></label></header>{loading ? <div className="employee-loading" aria-label="Loading employees"><span /><span /><span /></div> : list.length ? <div className="employee-table-wrap"><table><thead><tr><th>Employee</th><th>Role</th><th>Designation</th><th>Department</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{list.map((employee) => <tr key={employee.id}><td><div className="employee-cell"><span className="employee-avatar" aria-hidden="true">{employee.full_name.split(' ').map((part) => part[0]).join('').slice(0, 2)}</span><div><strong>{employee.full_name}</strong><small>{employee.employee_code} · {employee.company_email}</small></div></div></td><td><span className="role-badge">{roleLabel(employee.role)}</span></td><td>{employee.designation}</td><td>{employee.department}</td><td><span className={'employee-status ' + (employee.is_active ? 'active' : 'inactive')}>{employee.is_active ? 'Active' : 'Inactive'}</span></td><td><div className="employee-row-actions"><button type="button" className="button-secondary button-small" disabled={busy} onClick={() => { setEditing({ ...employee }); setCreateOpen(false); }}><Pencil size={14} /> Edit</button><button type="button" className="button-secondary button-small" disabled={busy} onClick={() => void toggleActive(employee)}>{employee.is_active ? 'Deactivate' : 'Reactivate'}</button></div></td></tr>)}</tbody></table></div> : <div className="employee-empty"><Users size={25} /><h3>{query ? 'No matching employees' : 'No employees found'}</h3><p>{query ? 'Try a different employee name, code, or email.' : 'Employee records will appear here.'}</p></div>}</section>
  </main>;
}
