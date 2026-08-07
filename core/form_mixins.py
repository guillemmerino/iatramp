from django import forms


class PlatformFormMixin:
    """Apply the shared platform styling to standard form controls."""

    def _decorate_fields(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                continue
            widget.attrs.setdefault("class", "platform-form-control")

