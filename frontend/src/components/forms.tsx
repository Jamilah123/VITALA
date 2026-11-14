import {
  useEffect,
  useId,
  useRef,
  type Dispatch,
  type FormEvent,
  type InputHTMLAttributes,
  type ReactNode,
  type SetStateAction,
} from "react";
import { formatDate, isValidIsoDate, todayIso } from "../lib/dates";
import type { FieldErrors } from "../lib/validation";

/** For a form's onChange: drop a field's error as soon as the user edits that field. */
export function clearErrorOnEdit(setErrors: Dispatch<SetStateAction<FieldErrors>>) {
  return (event: FormEvent<HTMLFormElement>) => {
    const { name } = event.target as HTMLInputElement;
    setErrors((previous) => {
      if (!(name in previous)) return previous;
      const remaining = { ...previous };
      delete remaining[name];
      return remaining;
    });
  };
}

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange"> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
  suffix?: string;
}

/** The PDF's field: value on the right, label on the left, inside one rounded row. */
export function Field({ label, value, onChange, error, hint, suffix, ...input }: FieldProps) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="field">
      <label className={`field__row${error ? " field__row--invalid" : ""}`} htmlFor={id}>
        <input
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...input}
        />
        {suffix && <span className="field__suffix">{suffix}</span>}
        <span className="field__label">{label}</span>
      </label>
      {hint && !error && (
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field__error" id={`${id}-error`} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

/** Browsers show date inputs in their own format, so spell the chosen date out too. */
export function DateField({ hint, ...props }: Omit<FieldProps, "type">) {
  const spelled = isValidIsoDate(props.value) ? formatDate(props.value) : undefined;
  return <Field type="date" max={todayIso()} hint={spelled ?? hint} {...props} />;
}

export function SelectField({
  name,
  label,
  value,
  onChange,
  error,
  hint,
  disabled,
  children,
}: {
  name?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
  disabled?: boolean;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="field">
      <label className={`field__row${error ? " field__row--invalid" : ""}`} htmlFor={id}>
        <select
          id={id}
          name={name}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
        >
          {children}
        </select>
        <span className="field__label">{label}</span>
      </label>
      {hint && !error && <p className="field__hint">{hint}</p>}
      {error && (
        <p className="field__error" id={`${id}-error`} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function Chip({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" className={`chip${selected ? " chip--on" : ""}`} aria-pressed={selected} onClick={onClick}>
      {children}
    </button>
  );
}

export function SegmentedField<T extends string>({
  legend,
  options,
  value,
  onChange,
  error,
}: {
  legend: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  error?: string;
}) {
  return (
    <fieldset className="segmented">
      <legend>{legend}</legend>
      <div className="chips">
        {options.map((option) => (
          <Chip key={option.value} selected={value === option.value} onClick={() => onChange(option.value)}>
            {option.label}
          </Chip>
        ))}
      </div>
      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}

export function CheckRow({
  checked,
  onChange,
  children,
  icon,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <label className="check-row">
      {icon}
      <span className="check-row__body">{children}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <h2 id={titleId} className="modal__title">
        {title}
      </h2>
      {children}
    </dialog>
  );
}
