from undo.models import Action


def _click(target, reason=""):
    return Action(type="click", x=1, y=1, target=target, reason=reason)


def test_restore_button_on_deleted_note_needs_no_confirmation():
    assert not _click("Bouton 'Restaurer' à côté de la note supprimée", "restaurer la note supprimée").needs_confirmation
    assert not _click("Restore deleted item").needs_confirmation


def test_destructive_buttons_still_confirm():
    assert _click("Bouton Supprimer").needs_confirmation
    assert _click("Vider la corbeille / Delete forever").needs_confirmation
    assert _click("Envoyer la demande").needs_confirmation
