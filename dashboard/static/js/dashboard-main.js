function loadComponents(components) {
    components.forEach(function(component) {
        return GenericApplication('.content .weave-small-cards-row', component);
    });
}

$(document).ready(function() {
    DEBUG_APPS = [];
    registerComponent('vertical-layout', '#template-vertical-layout');
    registerComponent('header-3', '#template-h3');
    registerComponent('paragraph', '#template-paragraph');
    registerComponent('weave-button', '#template-button');
    $.ajax({
        url: "/api/status-cards",
        dataType: "json"
    }).then(function(statusResponse) {
        loadComponents(statusResponse.cards);
    });
});
