import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import { ApiError, errorMessage } from "../api/errors";
import type { CatalogueMedication, MedicationUse } from "../api/types";
import { formatDate } from "../lib/dates";
import { drugClassLabel } from "../lib/profile";
import { useAsync } from "../lib/useAsync";
import { validateMedication, type FieldErrors, type MedicationInput } from "../lib/validation";
import { ErrorState, FormError, Loading, useToast } from "./feedback";
import { clearErrorOnEdit, DateField, Field, Modal, SelectField } from "./forms";
import { Icon } from "./Icon";

type Editing = { mode: "add" } | { mode: "edit"; use: MedicationUse };

function MedicationForm({
  editing,
  patientId,
  birthDate,
  catalogue,
  uses,
  onSaved,
  onClose,
}: {
  editing: Editing;
  patientId: number;
  birthDate: string | null;
  catalogue: CatalogueMedication[];
  uses: MedicationUse[];
  onSaved: () => void;
  onClose: () => void;
}) {
  const existing = editing.mode === "edit" ? editing.use : null;
  const [input, setInput] = useState<MedicationInput>({
    medication_id: existing?.medication_id ?? "",
    dose_text: existing?.dose_text ?? "",
    start_date: existing?.start_date ?? "",
    last_dose_change_date: existing?.last_dose_change_date ?? "",
  });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = (field: keyof MedicationInput) => (value: string) => setInput((previous) => ({ ...previous, [field]: value }));
  const selected = catalogue.find((medication) => medication.id === input.medication_id);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const takenIds = existing ? [] : uses.map((use) => use.medication_id);
    const found = validateMedication(input, birthDate, takenIds);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;

    const fields = {
      dose_text: input.dose_text.trim(),
      start_date: input.start_date || null,
      last_dose_change_date: input.last_dose_change_date || null,
    };
    setSaving(true);
    try {
      if (existing) await api.updateMedication(patientId, existing.id, fields);
      else await api.addMedication(patientId, { medication_id: input.medication_id, ...fields });
      onSaved();
    } catch (error) {
      if (error instanceof ApiError) setErrors(error.fieldErrors);
      setFormError(errorMessage(error));
      setSaving(false);
    }
  };

  return (
    <Modal title={existing ? "تعديل الدواء" : "إضافة دواء"} onClose={onClose}>
      <form onSubmit={submit} onChange={clearErrorOnEdit(setErrors)} noValidate className="stack">
        {existing ? (
          <p className="modal__subject">{selected ? `${selected.name_ar} (${selected.generic_name})` : existing.medication_id}</p>
        ) : (
          <SelectField
            name="medication_id"
            label="الدواء"
            value={input.medication_id}
            onChange={set("medication_id")}
            error={errors.medication_id}
            hint="قائمة أولية محدودة من الخادم، وليست شاملة لكل الأدوية."
          >
            <option value="">اختيار من القائمة</option>
            {catalogue.map((medication) => (
              <option key={medication.id} value={medication.id}>
                {medication.name_ar} ({medication.generic_name})
              </option>
            ))}
          </SelectField>
        )}
        {selected && <p className="field__hint">الفئة: {drugClassLabel(selected.drug_class)}</p>}
        <Field
          name="dose_text"
          label="الجرعة"
          value={input.dose_text}
          onChange={set("dose_text")}
          error={errors.dose_text}
          maxLength={200}
          placeholder="500 ملغ مرتين يومياً"
        />
        <DateField name="start_date" label="تاريخ البدء" value={input.start_date} onChange={set("start_date")} error={errors.start_date} />
        <DateField
          name="last_dose_change_date"
          label="آخر تغيير للجرعة"
          value={input.last_dose_change_date}
          onChange={set("last_dose_change_date")}
          error={errors.last_dose_change_date}
        />
        <FormError message={formError} />
        <div className="btn-row">
          <button type="button" className="btn btn--outline" onClick={onClose} disabled={saving}>
            إلغاء
          </button>
          <button type="submit" className="btn btn--primary btn--grow" disabled={saving}>
            {saving ? "جارٍ الحفظ…" : "حفظ"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function RemoveDialog({
  name,
  patientId,
  useId,
  onRemoved,
  onClose,
}: {
  name: string;
  patientId: number;
  useId: number;
  onRemoved: () => void;
  onClose: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const remove = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.removeMedication(patientId, useId);
      onRemoved();
    } catch (failure) {
      setError(errorMessage(failure));
      setSaving(false);
    }
  };

  return (
    <Modal title="حذف الدواء" onClose={onClose}>
      <p className="stack-text">هل تريد حذف {name} من الملف؟ لا يمكن التراجع عن الحذف.</p>
      <FormError message={error} />
      <div className="btn-row">
        <button type="button" className="btn btn--outline" onClick={onClose} disabled={saving}>
          إلغاء
        </button>
        <button type="button" className="btn btn--danger btn--grow" onClick={remove} disabled={saving}>
          {saving ? "جارٍ الحذف…" : "حذف"}
        </button>
      </div>
    </Modal>
  );
}

/** The patient's medication list, read and changed through the API. */
export function MedicationManager({ patientId, birthDate }: { patientId: number; birthDate: string | null }) {
  const toast = useToast();
  const [editing, setEditing] = useState<Editing | null>(null);
  const [removing, setRemoving] = useState<MedicationUse | null>(null);

  const state = useAsync(
    async (signal) => {
      const [uses, catalogue] = await Promise.all([api.listMedications(patientId, signal), api.listCatalogue(signal)]);
      return { uses, catalogue };
    },
    [patientId],
  );

  if (state.loading && !state.data) return <Loading label="جارٍ تحميل الأدوية…" />;
  if (state.error || !state.data) return <ErrorState error={state.error} onRetry={state.reload} />;

  const { uses, catalogue } = state.data;
  const nameOf = (use: MedicationUse) => catalogue.find((item) => item.id === use.medication_id)?.name_ar ?? use.medication_id;

  return (
    <div className="stack">
      {uses.length === 0 && <p className="empty">لا توجد أدوية مسجّلة في ملفك.</p>}
      <ul className="med-list">
        {uses.map((use) => (
          <li key={use.id} className="med">
            <div className="med__body">
              <strong>
                {nameOf(use)} <bdi>{use.dose_text}</bdi>
              </strong>
              {(use.start_date || use.last_dose_change_date) && (
                <span className="muted small">
                  {use.start_date && `البدء: ${formatDate(use.start_date)}`}
                  {use.start_date && use.last_dose_change_date && " · "}
                  {use.last_dose_change_date && `آخر تغيير: ${formatDate(use.last_dose_change_date)}`}
                </span>
              )}
            </div>
            <div className="med__actions">
              <button type="button" className="link-btn" onClick={() => setEditing({ mode: "edit", use })}>
                تعديل
              </button>
              <button type="button" className="link-btn link-btn--danger" onClick={() => setRemoving(use)}>
                حذف
              </button>
            </div>
          </li>
        ))}
      </ul>
      <button type="button" className="add-row" onClick={() => setEditing({ mode: "add" })}>
        <Icon name="plus" size={18} /> إضافة دواء
      </button>

      {editing && (
        <MedicationForm
          editing={editing}
          patientId={patientId}
          birthDate={birthDate}
          catalogue={catalogue}
          uses={uses}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            state.reload();
            toast("حُفظ الدواء في الخادم.");
          }}
        />
      )}
      {removing && (
        <RemoveDialog
          name={nameOf(removing)}
          patientId={patientId}
          useId={removing.id}
          onClose={() => setRemoving(null)}
          onRemoved={() => {
            setRemoving(null);
            state.reload();
            toast("حُذف الدواء من الخادم.");
          }}
        />
      )}
    </div>
  );
}
