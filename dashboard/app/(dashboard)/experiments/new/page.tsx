import { NewExperimentForm } from "./form";

export default function NewExperimentPage() {
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">New experiment</h1>
      <p className="mt-1 text-sm text-muted">
        Each variant is a JSON config your app reads: a prompt, a model, parameters, anything.
        The first variant is the control.
      </p>
      <NewExperimentForm />
    </div>
  );
}
