function loadComponents(components) {
    components.forEach(function(component) {
        return GenericApplication('.content .weave-medium-cards-row', component);
    });
}

$(document).ready(function() {
    Vue.config.errorHandler = function (msg, vm, trace) {
      console.log(msg, trace);
    }
    Vue.config.warnHandler = function (msg, vm, trace) {
      console.log(msg, trace);
    }
    registerComponent('vertical-layout', '#template-vertical-layout');
    registerComponent('header-3', '#template-h3');
    registerComponent('paragraph', '#template-paragraph');
    registerComponent('weave-button', '#template-button');
    registerComponent('medium-card', '#template-medium-card');
    registerComponent('card-footer-status', '#template-card-footer-status');
    registerComponent('weave-icon', '#template-weave-icon');
    $.ajax({
        url: "/api/status-cards",
        dataType: "json"
    }).then(function(statusResponse) {
        loadComponents(statusResponse.cards);
    });
});
